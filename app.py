import ast
import csv
import glob
import io
import os
import shutil
import sqlite3 as _sqlite3
from urllib.parse import quote as url_quote
import json
import random
import subprocess
import tempfile
from datetime import datetime, date, timedelta, timezone
from functools import wraps

_MSK_OFFSET = timezone(timedelta(hours=3))

def now_msk():
    return datetime.now(_MSK_OFFSET).replace(tzinfo=None)

def utc_to_msk(dt):
    return (dt + timedelta(hours=3)).strftime('%H:%M') if dt else ''

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, session, make_response)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from models import (db, User, Module, Level, UserProgress, Group, GroupMember,
                    Assignment, Submission, Message, Achievement,
                    UserAchievement, Avatar, Case, UserAvatar, Note,
                    LibraryArticle)

_BASE_DIR = os.path.dirname(__file__)
BACKUP_DIR = os.path.join(_BASE_DIR, 'backups')
DB_PATH    = os.path.join(_BASE_DIR, 'instance', 'platform.db')
MAX_BACKUPS = 20


def create_backup(label='auto'):
    """Safe hot-copy of the SQLite DB using sqlite3.backup()."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
    name = f'backup_{label}_{ts}.db'
    dest = os.path.join(BACKUP_DIR, name)
    src_conn = _sqlite3.connect(DB_PATH)
    dst_conn = _sqlite3.connect(dest)
    src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()
    # keep only MAX_BACKUPS newest files
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, 'backup_*.db')))
    while len(files) > MAX_BACKUPS:
        os.remove(files.pop(0))
    return name


app = Flask(__name__)
app.config['SECRET_KEY'] = 'pylearn-secret-2024-xK9mN3'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///platform.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'txt', 'py',
    'jpg', 'jpeg', 'png', 'gif',
    'zip', 'xlsx', 'xls', 'pptx', 'ppt',
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db.init_app(app)

# ── Auto-backup scheduler ────────────────────────────────────────────────────
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

def _start_backup_scheduler():
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(create_backup, 'interval', hours=6, args=['auto'],
                  id='auto_backup', replace_existing=True)
    sched.start()
    atexit.register(lambda: sched.shutdown(wait=False))

# Start only in the real worker process, not Flask's reloader monitor
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
    _start_backup_scheduler()

# Jinja2 custom filters
@app.template_filter('msk_time')
def msk_time_filter(dt):
    return utc_to_msk(dt)

@app.template_filter('rarity_ru')
def rarity_ru_filter(r):
    return {'common': 'Обычная', 'rare': 'Редкая', 'epic': 'Эпическая', 'legendary': 'Легендарная'}.get(r, r)

@app.template_filter('msk_dt')
def msk_dt_filter(dt):
    return (dt + timedelta(hours=3)).strftime('%d.%m %H:%M') if dt else ''

@app.template_filter('enumerate')
def jinja_enumerate(iterable):
    return enumerate(iterable)

@app.template_filter('msk')
def jinja_msk(dt):
    if dt is None:
        return ''
    return dt + timedelta(hours=3)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Войдите в систему для доступа к платформе'


@app.before_request
def check_daily_login_bonus():
    if not current_user.is_authenticated or current_user.role != 'student':
        return
    if request.path.startswith('/api/'):
        return
    bonus = _grant_daily_login_bonus(current_user)
    if bonus:
        flash(f'Бонус за ежедневный вход: +{bonus} XP!', 'success')

DAILY_LOGIN_BONUS_XP = 10

RANK_TIERS = [
    (0.03, '🌱', 'Росток'),
    (0.07, '🐣', 'Птенчик'),
    (0.12, '⚡', 'Заряд'),
    (0.18, '🌟', 'Новичок'),
    (0.25, '🐱', 'Кодёнок'),
    (0.33, '🔥', 'Горячо!'),
    (0.41, '💫', 'Вспышка'),
    (0.49, '🎯', 'Стрелок'),
    (0.56, '💎', 'Алмаз'),
    (0.63, '🚀', 'Ракета'),
    (0.70, '🏅', 'Медаль'),
    (0.76, '🏆', 'Чемпион'),
    (0.82, '🌊', 'Прибой'),
    (0.87, '👑', 'Корона'),
    (0.91, '🌈', 'Радуга'),
    (0.94, '🦁', 'Лев'),
    (0.96, '🐉', 'Дракон'),
    (0.98, '⭐', 'Суперзвезда'),
    (0.99, '🔮', 'Мастер'),
    (1.00, '🐱', 'КодиК!'),
]

def _compute_rank(total_xp, max_xp):
    icon, label = '🥚', 'Новобранец'
    for pct, t_icon, t_label in RANK_TIERS:
        if total_xp >= round(pct * max_xp):
            icon, label = t_icon, t_label
    return icon, label


@app.context_processor
def inject_nav_counts():
    counts = {'nav_unread_msgs': 0, 'nav_pending_assignments': 0,
              'nav_rank_icon': '', 'nav_rank_label': ''}
    if current_user.is_authenticated:
        counts['nav_unread_msgs'] = Message.query.filter_by(
            receiver_id=current_user.id, read=False).count()
        if current_user.role == 'student':
            assignments = _get_student_assignments()
            submitted_ids = {
                s.assignment_id for s in
                Submission.query.filter_by(student_id=current_user.id).all()
            }
            counts['nav_pending_assignments'] = sum(
                1 for a in assignments if a.id not in submitted_ids
            )
            from sqlalchemy import func as _sqlfunc
            max_xp = db.session.query(_sqlfunc.sum(Level.xp_reward)).scalar() or 10000
            icon, label = _compute_rank(current_user.total_xp, max_xp)
            counts['nav_rank_icon'] = icon
            counts['nav_rank_label'] = label
    return counts


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                flash('Доступ запрещён', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Неверный email или пароль', 'danger')
    return render_template('auth/login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form.get('role', 'student')
        if role not in ('student', 'parent'):
            role = 'student'
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if len(username) < 3:
            flash('Имя пользователя должно содержать минимум 3 символа.', 'danger')
            return render_template('auth/register.html')
        if len(password) < 6:
            flash('Пароль должен содержать минимум 6 символов.', 'danger')
            return render_template('auth/register.html')
        if User.query.filter_by(email=request.form['email']).first():
            flash('Email уже зарегистрирован', 'danger')
            return render_template('auth/register.html')
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя занято', 'danger')
            return render_template('auth/register.html')
        user = User(
            username=username,
            email=request.form['email'],
            password_hash=generate_password_hash(password),
            role=role
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Добро пожаловать на КодиК! 🐱', 'success')
        return redirect(url_for('dashboard'))
    return render_template('auth/register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'student':
        return redirect(url_for('student_dashboard'))
    elif current_user.role == 'teacher':
        return redirect(url_for('teacher_dashboard'))
    elif current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif current_user.role == 'parent':
        return redirect(url_for('parent_dashboard'))
    return redirect(url_for('login'))


# ── Student ───────────────────────────────────────────────────────────────────

@app.route('/student')
@login_required
@role_required('student')
def student_dashboard():
    completed = UserProgress.query.filter_by(
        user_id=current_user.id, status='completed').count()
    total_levels = Level.query.count()
    achievements = UserAchievement.query.filter_by(
        user_id=current_user.id).order_by(UserAchievement.earned_at.desc()).limit(3).all()
    all_earned = UserAchievement.query.filter_by(
        user_id=current_user.id).order_by(UserAchievement.earned_at.desc()).all()
    earned_ids = {ua.achievement_id for ua in all_earned}
    all_achievements = Achievement.query.order_by(Achievement.id).all()
    assignments = _get_student_assignments()
    top_students = User.query.filter_by(role='student').order_by(User.total_xp.desc()).limit(10).all()
    all_students = User.query.filter_by(role='student').order_by(User.total_xp.desc()).all()
    my_rank = next((i+1 for i, u in enumerate(all_students) if u.id == current_user.id), None)
    my_notes = Note.query.filter_by(student_id=current_user.id)\
                         .order_by(Note.created_at.desc()).limit(10).all()
    memberships = GroupMember.query.filter_by(user_id=current_user.id).all()
    student_groups = []
    seen_gids = set()
    for m in memberships:
        if m.group_id in seen_gids:
            continue
        seen_gids.add(m.group_id)
        group = Group.query.get(m.group_id)
        if not group:
            continue
        member_ids = [gm.user_id for gm in group.members]
        group_top = User.query.filter(
            User.id.in_(member_ids), User.role == 'student'
        ).order_by(User.total_xp.desc()).limit(10).all()
        all_in_group = User.query.filter(
            User.id.in_(member_ids), User.role == 'student'
        ).order_by(User.total_xp.desc()).all()
        my_group_rank = next(
            (i + 1 for i, u in enumerate(all_in_group) if u.id == current_user.id), None
        )
        student_groups.append({
            'group': group,
            'students': group_top,
            'my_rank': my_group_rank
        })
    return render_template('student/dashboard.html',
                           completed=completed,
                           total_levels=total_levels,
                           achievements=achievements,
                           all_earned=all_earned,
                           earned_ids=earned_ids,
                           all_achievements=all_achievements,
                           assignments=assignments,
                           top_students=top_students,
                           my_rank=my_rank,
                           my_notes=my_notes,
                           student_groups=student_groups)


def _get_student_assignments():
    from sqlalchemy import or_, and_
    memberships = GroupMember.query.filter_by(user_id=current_user.id).all()
    group_ids = [m.group_id for m in memberships]
    if not group_ids:
        return []
    teacher_ids = [g.teacher_id for g in Group.query.filter(Group.id.in_(group_ids)).all() if g.teacher_id]
    return Assignment.query.filter(
        or_(
            Assignment.group_id.in_(group_ids),
            and_(Assignment.group_id.is_(None), Assignment.teacher_id.in_(teacher_ids))
        )
    ).order_by(Assignment.created_at.desc()).limit(5).all()


@app.route('/student/levelmap')
@login_required
@role_required('student')
def student_levelmap():
    all_modules = Module.query.order_by(Module.order).all()
    modules = [m for m in all_modules if not m.is_bonus]
    bonus_modules = [m for m in all_modules if m.is_bonus]
    progress_map = {}
    for m in all_modules:
        total = len(m.levels)
        done = sum(
            1 for lv in m.levels
            if UserProgress.query.filter_by(
                user_id=current_user.id, level_id=lv.id, status='completed').first()
        )
        progress_map[m.id] = {'total': total, 'done': done}
    return render_template('student/levelmap.html',
                           modules=modules,
                           bonus_modules=bonus_modules,
                           progress_map=progress_map)


@app.route('/student/chat')
@login_required
@role_required('student')
def student_chat():
    memberships = GroupMember.query.filter_by(user_id=current_user.id).all()
    group_ids = [m.group_id for m in memberships]
    teacher_ids = set()
    if group_ids:
        groups = Group.query.filter(Group.id.in_(group_ids)).all()
        teacher_ids = {g.teacher_id for g in groups if g.teacher_id}
    contacts = User.query.filter(User.id.in_(teacher_ids)).all() if teacher_ids else []
    contact_id = request.args.get('with', type=int)
    messages = []
    if contact_id:
        messages = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == contact_id)) |
            ((Message.sender_id == contact_id) & (Message.receiver_id == current_user.id))
        ).order_by(Message.created_at).all()
        Message.query.filter_by(receiver_id=current_user.id, sender_id=contact_id, read=False)\
                     .update({'read': True})
        db.session.commit()
    unread_rows = db.session.query(Message.sender_id, db.func.count(Message.id))\
        .filter_by(receiver_id=current_user.id, read=False)\
        .group_by(Message.sender_id).all()
    unread_by_sender = {r[0]: r[1] for r in unread_rows}
    return render_template('student/chat.html', contacts=contacts,
                           messages=messages, contact_id=contact_id,
                           unread_by_sender=unread_by_sender)


@app.route('/student/battlepass')
@login_required
@role_required('student')
def student_battlepass():
    from sqlalchemy import func
    max_xp = db.session.query(func.sum(Level.xp_reward)).scalar() or 10000
    return render_template('student/battlepass.html',
                           user_xp=current_user.total_xp,
                           max_xp=max_xp)


@app.route('/student/library')
@login_required
@role_required('student')
def student_library():
    modules = Module.query.filter_by(is_bonus=False).order_by(Module.order).all()
    module_theories = {
        m.id: next((lv for lv in m.levels if lv.type == 'theory'), None)
        for m in modules
    }
    articles = LibraryArticle.query.order_by(LibraryArticle.category, LibraryArticle.order).all()
    lib_categories = {}
    for a in articles:
        lib_categories.setdefault(a.category, []).append(a)
    return render_template('student/library.html', modules=modules,
                           module_theories=module_theories,
                           lib_categories=lib_categories)


@app.route('/student/module/<int:module_id>')
@login_required
@role_required('student')
def student_module(module_id):
    module = Module.query.get_or_404(module_id)
    levels = Level.query.filter_by(module_id=module_id).order_by(Level.order).all()
    progress = {
        p.level_id: p.status
        for p in UserProgress.query.filter_by(user_id=current_user.id).all()
    }
    # unlock: first level always open; rest require previous to be complete
    for i, lv in enumerate(levels):
        if i == 0:
            lv.unlocked = True
        else:
            lv.unlocked = progress.get(levels[i - 1].id) == 'completed'
        lv.status = progress.get(lv.id, 'not_started')
    return render_template('student/module.html', module=module, levels=levels)


@app.route('/student/level/<int:level_id>')
@login_required
@role_required('student')
def student_level(level_id):
    level = Level.query.get_or_404(level_id)
    progress = UserProgress.query.filter_by(
        user_id=current_user.id, level_id=level_id).first()
    blocks_config = json.loads(level.blocks_config) if level.blocks_config else {}
    module_theory = Level.query.filter_by(
        module_id=level.module_id, type='theory'
    ).order_by(Level.order).first()
    module_theory_content = module_theory.theory_content if module_theory else None
    next_level = Level.query.filter_by(module_id=level.module_id)\
        .filter(Level.order > level.order)\
        .order_by(Level.order).first()
    return render_template('student/level.html',
                           level=level,
                           progress=progress,
                           blocks_config=blocks_config,
                           difficulty=current_user.difficulty,
                           module_theory_content=module_theory_content,
                           next_level=next_level)


@app.route('/student/shop')
@login_required
@role_required('student')
def student_shop():
    cases = Case.query.all()
    owned_ids = {ua.avatar_id for ua in UserAvatar.query.filter_by(user_id=current_user.id).all()}
    avatars = Avatar.query.filter_by(case_id=None).all()
    for av in avatars:
        av.owned = av.id in owned_ids
    return render_template('student/shop.html', cases=cases, avatars=avatars, owned_ids=owned_ids)


@app.route('/student/assignments')
@login_required
@role_required('student')
def student_assignments():
    assignments = _get_student_assignments()
    my_subs = {s.assignment_id: s for s in Submission.query.filter_by(student_id=current_user.id).all()}
    return render_template('student/assignments.html',
                           assignments=assignments,
                           my_subs=my_subs)


@app.route('/student/sandbox')
@login_required
@role_required('student')
def student_sandbox():
    return render_template('student/sandbox.html')


# ── Teacher ───────────────────────────────────────────────────────────────────

@app.route('/teacher')
@login_required
@role_required('teacher')
def teacher_dashboard():
    groups = Group.query.filter_by(teacher_id=current_user.id).all()
    assignments = Assignment.query.filter_by(teacher_id=current_user.id)\
                                  .order_by(Assignment.created_at.desc()).all()
    pending = Submission.query.join(Assignment)\
                              .filter(Assignment.teacher_id == current_user.id,
                                      Submission.status == 'submitted').count()
    member_ids = [m.user_id for g in groups for m in g.members]
    students = User.query.filter(User.id.in_(member_ids)).order_by(User.username).all() if member_ids else []
    recent_notes = Note.query.filter_by(teacher_id=current_user.id)\
                             .order_by(Note.created_at.desc()).limit(20).all()
    return render_template('teacher/dashboard.html',
                           groups=groups,
                           assignments=assignments,
                           pending=pending,
                           students=students,
                           recent_notes=recent_notes)


@app.route('/teacher/note/add', methods=['POST'])
@login_required
@role_required('teacher')
def teacher_add_note():
    student_id = request.form.get('student_id', type=int)
    content = request.form.get('content', '').strip()
    note_type = request.form.get('type', 'remark')
    if student_id and content:
        note = Note(student_id=student_id, teacher_id=current_user.id,
                    content=content, type=note_type)
        db.session.add(note)
        db.session.commit()
        flash('Замечание добавлено!', 'success')
    return redirect(url_for('teacher_dashboard'))


@app.route('/teacher/note/<int:note_id>/delete', methods=['POST'])
@login_required
@role_required('teacher')
def teacher_delete_note(note_id):
    note = Note.query.get_or_404(note_id)
    if note.teacher_id == current_user.id:
        db.session.delete(note)
        db.session.commit()
    return redirect(url_for('teacher_dashboard'))


@app.route('/teacher/assignment/new', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def teacher_new_assignment():
    groups = Group.query.filter_by(teacher_id=current_user.id).all()
    if request.method == 'POST':
        due = None
        if request.form.get('due_date'):
            try:
                due = datetime.strptime(request.form['due_date'], '%Y-%m-%dT%H:%M')
                if due <= now_msk():
                    flash('Срок сдачи должен быть в будущем.', 'danger')
                    return render_template('teacher/new_assignment.html', groups=groups)
            except ValueError:
                flash('Некорректный формат даты.', 'danger')
                return render_template('teacher/new_assignment.html', groups=groups)
        file_path = None
        if 'file' in request.files:
            f = request.files['file']
            if f.filename:
                filename = secure_filename(f.filename)
                assign_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'assignments')
                os.makedirs(assign_dir, exist_ok=True)
                f.save(os.path.join(assign_dir, filename))
                file_path = filename
        a = Assignment(
            teacher_id=current_user.id,
            group_id=request.form.get('group_id') or None,
            title=request.form['title'],
            description=request.form['description'],
            due_date=due,
            file_path=file_path
        )
        db.session.add(a)
        db.session.commit()
        flash('Задание создано!', 'success')
        return redirect(url_for('teacher_dashboard'))
    return render_template('teacher/new_assignment.html', groups=groups)


@app.route('/teacher/submissions')
@login_required
@role_required('teacher')
def teacher_submissions():
    assignments = (Assignment.query
                   .filter_by(teacher_id=current_user.id)
                   .order_by(Assignment.created_at.desc())
                   .all())
    subs_map = {}
    for a in assignments:
        subs_map[a.id] = sorted(a.submissions, key=lambda s: s.submitted_at, reverse=True)
    return render_template('teacher/submissions.html',
                           assignments=assignments, subs_map=subs_map)


@app.route('/teacher/submission/<int:sub_id>/grade', methods=['POST'])
@login_required
@role_required('teacher')
def teacher_grade(sub_id):
    sub = Submission.query.get_or_404(sub_id)
    grade_raw = request.form.get('grade', '').strip()
    try:
        grade_val = int(grade_raw)
        if grade_val < 1:
            raise ValueError
    except ValueError:
        flash('Оценка должна быть целым положительным числом.', 'danger')
        return redirect(url_for('teacher_submissions'))
    sub.grade = str(grade_val)
    sub.feedback = request.form.get('feedback', '')
    sub.status = 'graded'
    db.session.commit()
    flash('Оценка выставлена!', 'success')
    return redirect(url_for('teacher_submissions'))


@app.route('/teacher/assignment/<int:assignment_id>/toggle-close', methods=['POST'])
@login_required
@role_required('teacher')
def teacher_toggle_close(assignment_id):
    a = Assignment.query.get_or_404(assignment_id)
    if a.teacher_id != current_user.id:
        flash('Нет доступа.', 'danger')
        return redirect(url_for('teacher_submissions'))
    a.is_closed = not a.is_closed
    db.session.commit()
    flash('Приём работ закрыт.' if a.is_closed else 'Приём работ снова открыт.', 'success')
    return redirect(url_for('teacher_submissions'))


@app.route('/api/teacher/assignment/<int:assignment_id>/edit', methods=['POST'])
@login_required
@role_required('teacher')
def api_teacher_edit_assignment(assignment_id):
    a = Assignment.query.get_or_404(assignment_id)
    if a.teacher_id != current_user.id:
        return jsonify({'error': 'Нет доступа'}), 403
    data = request.get_json()
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'Название обязательно'}), 400
    a.title = title
    a.description = (data.get('description') or '').strip()
    group_id = data.get('group_id')
    a.group_id = int(group_id) if group_id else None
    due_str = (data.get('due_date') or '').strip()
    if due_str:
        try:
            a.due_date = datetime.strptime(due_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            return jsonify({'error': 'Некорректный формат даты'}), 400
    else:
        a.due_date = None
    db.session.commit()
    return jsonify({
        'ok': True,
        'title': a.title,
        'description': a.description or '',
        'group_id': a.group_id,
        'group_name': a.group.name if a.group else None,
        'due_date': a.due_date.strftime('%Y-%m-%dT%H:%M') if a.due_date else None,
        'due_display': a.due_date.strftime('%d.%m.%Y %H:%M') if a.due_date else None,
        'is_closed': a.is_closed
    })


@app.route('/api/teacher/assignment/<int:assignment_id>/delete', methods=['POST'])
@login_required
@role_required('teacher')
def api_teacher_delete_assignment(assignment_id):
    a = Assignment.query.get_or_404(assignment_id)
    if a.teacher_id != current_user.id:
        return jsonify({'error': 'Нет доступа'}), 403
    Submission.query.filter_by(assignment_id=a.id).delete()
    db.session.delete(a)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/teacher/file/<path:filename>')
@login_required
@role_required('teacher')
def teacher_download_file(filename):
    from flask import send_from_directory
    upload_dir = app.config['UPLOAD_FOLDER']
    return send_from_directory(upload_dir, filename, as_attachment=True)


@app.route('/assignment/file/<path:filename>')
@login_required
def assignment_download_file(filename):
    from flask import send_from_directory
    assign_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'assignments')
    return send_from_directory(assign_dir, filename, as_attachment=True)


@app.route('/teacher/chat')
@login_required
@role_required('teacher')
def teacher_chat():
    memberships = GroupMember.query.join(Group).filter(
        Group.teacher_id == current_user.id).all()
    students = [User.query.get(m.user_id) for m in memberships]
    students = list({s.id: s for s in students if s}.values())
    parent_ids = {s.parent_id for s in students if s.parent_id}
    parents = User.query.filter(User.id.in_(parent_ids)).all() if parent_ids else []
    admins = User.query.filter_by(role='admin').all()
    contacts = students + parents + admins
    contact_id = request.args.get('with', type=int)
    messages = []
    if contact_id:
        messages = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == contact_id)) |
            ((Message.sender_id == contact_id) & (Message.receiver_id == current_user.id))
        ).order_by(Message.created_at).all()
        Message.query.filter_by(receiver_id=current_user.id, sender_id=contact_id, read=False)\
                     .update({'read': True})
        db.session.commit()
    unread_rows = db.session.query(Message.sender_id, db.func.count(Message.id))\
        .filter_by(receiver_id=current_user.id, read=False)\
        .group_by(Message.sender_id).all()
    unread_by_sender = {r[0]: r[1] for r in unread_rows}
    return render_template('teacher/chat.html',
                           students=students,
                           parents=parents,
                           admins=admins,
                           contacts=contacts,
                           messages=messages,
                           unread_by_sender=unread_by_sender,
                           contact_id=contact_id)


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.route('/admin')
@login_required
@role_required('admin')
def admin_dashboard():
    stats = {
        'students': User.query.filter_by(role='student').count(),
        'teachers': User.query.filter_by(role='teacher').count(),
        'parents': User.query.filter_by(role='parent').count(),
        'groups': Group.query.count(),
        'completions': UserProgress.query.filter_by(status='completed').count(),
        'assignments': Assignment.query.count(),
    }
    users = User.query.order_by(User.created_at.desc()).limit(20).all()
    groups = Group.query.all()
    teachers = User.query.filter_by(role='teacher').all()
    students = User.query.filter_by(role='student').all()
    top_students = User.query.filter_by(role='student').order_by(User.total_xp.desc()).limit(10).all()
    linked_students = User.query.filter(User.parent_id.isnot(None), User.role == 'student').all()
    linked_pairs = []
    for s in linked_students:
        parent = User.query.get(s.parent_id)
        if parent:
            linked_pairs.append({'parent': parent, 'child': s})
    # Stats per group for the group viewer
    group_student_stats = {}
    for g in groups:
        g_assignments = Assignment.query.filter_by(group_id=g.id).all()
        total_assignments = len(g_assignments)
        assign_ids = [a.id for a in g_assignments]
        member_ids = [m.user_id for m in g.members]
        rows = []
        for s in students:
            if s.id not in member_ids:
                continue
            completed = UserProgress.query.filter_by(user_id=s.id, status='completed').count()
            if assign_ids:
                submitted = Submission.query.filter(
                    Submission.student_id == s.id,
                    Submission.assignment_id.in_(assign_ids)
                ).count()
            else:
                submitted = 0
            rows.append({
                'id': s.id, 'username': s.username, 'avatar': s.avatar_emoji,
                'xp': s.total_xp, 'completed': completed,
                'submitted': submitted, 'total_assignments': total_assignments,
            })
        group_student_stats[g.id] = rows
    return render_template('admin/dashboard.html',
                           stats=stats, users=users, groups=groups,
                           teachers=teachers, students=students,
                           top_students=top_students, linked_pairs=linked_pairs,
                           group_student_stats=group_student_stats)


@app.route('/admin/group/new', methods=['POST'])
@login_required
@role_required('admin')
def admin_new_group():
    g = Group(name=request.form['name'],
              teacher_id=request.form.get('teacher_id') or None)
    db.session.add(g)
    db.session.commit()
    flash('Группа создана!', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/group/<int:group_id>/add_student', methods=['POST'])
@login_required
@role_required('admin')
def admin_add_student(group_id):
    student_id = int(request.form['student_id'])
    if not GroupMember.query.filter_by(group_id=group_id, user_id=student_id).first():
        db.session.add(GroupMember(group_id=group_id, user_id=student_id))
        db.session.commit()
    flash('Ученик добавлен в группу!', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/link-parent', methods=['POST'])
@login_required
@role_required('admin')
def admin_link_parent():
    parent_id = request.form.get('parent_id', type=int)
    student_id = request.form.get('student_id', type=int)
    if not parent_id or not student_id:
        flash('Выбери родителя и ученика', 'danger')
        return redirect(url_for('admin_dashboard'))
    student = User.query.get_or_404(student_id)
    student.parent_id = parent_id
    db.session.commit()
    flash('Аккаунты привязаны!', 'success')
    return redirect(url_for('admin_dashboard') + '#tab-links')


@app.route('/admin/unlink-parent/<int:student_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_unlink_parent(student_id):
    student = User.query.get_or_404(student_id)
    student.parent_id = None
    db.session.commit()
    flash('Привязка удалена', 'success')
    return redirect(url_for('admin_dashboard') + '#tab-links')


@app.route('/admin/chat')
@login_required
@role_required('admin')
def admin_chat():
    teachers = User.query.filter_by(role='teacher').all()
    parents = User.query.filter_by(role='parent').all()
    contacts = teachers + parents
    contact_id = request.args.get('with', type=int)
    messages = []
    if contact_id:
        messages = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == contact_id)) |
            ((Message.sender_id == contact_id) & (Message.receiver_id == current_user.id))
        ).order_by(Message.created_at).all()
        Message.query.filter_by(receiver_id=current_user.id, sender_id=contact_id, read=False)\
                     .update({'read': True})
        db.session.commit()
    unread_rows = db.session.query(Message.sender_id, db.func.count(Message.id))\
        .filter_by(receiver_id=current_user.id, read=False)\
        .group_by(Message.sender_id).all()
    unread_by_sender = {r[0]: r[1] for r in unread_rows}
    return render_template('admin/chat.html', teachers=teachers, parents=parents,
                           contacts=contacts, messages=messages, contact_id=contact_id,
                           unread_by_sender=unread_by_sender)


@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Нельзя удалить себя', 'danger')
        return redirect(url_for('admin_dashboard'))
    # Снимаем привязку родителя у детей
    User.query.filter_by(parent_id=user.id).update({'parent_id': None})
    # Удаляем все связанные записи
    UserAchievement.query.filter_by(user_id=user.id).delete()
    UserProgress.query.filter_by(user_id=user.id).delete()
    UserAvatar.query.filter_by(user_id=user.id).delete()
    GroupMember.query.filter_by(user_id=user.id).delete()
    Submission.query.filter_by(student_id=user.id).delete()
    Message.query.filter(
        (Message.sender_id == user.id) | (Message.receiver_id == user.id)
    ).delete()
    Note.query.filter(
        (Note.student_id == user.id) | (Note.teacher_id == user.id)
    ).delete()
    db.session.delete(user)
    db.session.commit()
    flash('Пользователь удалён', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/user/<int:user_id>/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({'error': 'Нельзя редактировать собственный аккаунт'}), 403
    data = request.get_json()
    new_username = (data.get('username') or '').strip()
    new_email = (data.get('email') or '').strip()
    new_role = (data.get('role') or '').strip()
    new_password = (data.get('password') or '').strip()
    if len(new_username) < 3:
        return jsonify({'error': 'Имя пользователя слишком короткое (мин. 3 символа)'}), 400
    if not new_email:
        return jsonify({'error': 'Email не может быть пустым'}), 400
    if new_role not in ('student', 'teacher', 'parent', 'admin'):
        return jsonify({'error': 'Недопустимая роль'}), 400
    if User.query.filter(User.username == new_username, User.id != user_id).first():
        return jsonify({'error': 'Имя пользователя уже занято'}), 400
    if User.query.filter(User.email == new_email, User.id != user_id).first():
        return jsonify({'error': 'Email уже используется'}), 400
    if new_password:
        if len(new_password) < 6:
            return jsonify({'error': 'Пароль должен содержать минимум 6 символов'}), 400
        user.password_hash = generate_password_hash(new_password)
    user.username = new_username
    user.email = new_email
    user.role = new_role
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/group/<int:group_id>/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_edit_group(group_id):
    group = Group.query.get_or_404(group_id)
    data = request.get_json()
    new_name = (data.get('name') or '').strip()
    if not new_name:
        return jsonify({'error': 'Название группы не может быть пустым'}), 400
    teacher_id = data.get('teacher_id') or None
    if teacher_id:
        teacher_id = int(teacher_id)
    group.name = new_name
    group.teacher_id = teacher_id
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/group/<int:group_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_delete_group(group_id):
    GroupMember.query.filter_by(group_id=group_id).delete()
    Assignment.query.filter_by(group_id=group_id).delete()
    Group.query.filter_by(id=group_id).delete()
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/group/<int:group_id>/remove_student', methods=['POST'])
@login_required
@role_required('admin')
def admin_remove_student_from_group(group_id):
    data = request.get_json()
    student_id = data.get('student_id')
    if not student_id:
        return jsonify({'error': 'student_id required'}), 400
    GroupMember.query.filter_by(group_id=group_id, user_id=int(student_id)).delete()
    db.session.commit()
    return jsonify({'ok': True})


# ── Admin exports ─────────────────────────────────────────────────────────────

def _csv_response(rows, filename):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    for row in rows:
        w.writerow(row)
    resp = make_response(buf.getvalue().encode('utf-8-sig'))
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    # RFC 5987: ASCII fallback + UTF-8 encoded name for Cyrillic filenames
    ascii_name = filename.encode('ascii', 'replace').decode('ascii').replace('?', '_')
    utf8_name = url_quote(filename, safe='')
    resp.headers['Content-Disposition'] = (
        f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"
    )
    return resp


@app.route('/admin/export/group/<int:group_id>')
@login_required
@role_required('admin')
def admin_export_group(group_id):
    group = Group.query.get_or_404(group_id)
    teacher = User.query.get(group.teacher_id) if group.teacher_id else None
    assignments = Assignment.query.filter_by(group_id=group_id).all()
    assign_ids = [a.id for a in assignments]
    member_ids = [m.user_id for m in group.members]
    students = (User.query.filter(User.id.in_(member_ids)).order_by(User.username).all()
                if member_ids else [])

    now_str = now_msk().strftime('%d.%m.%Y %H:%M')
    rows = [
        [f'Группа: {group.name}'],
        [f'Учитель: {teacher.username if teacher else "—"}'],
        [f'Дата выгрузки: {now_str}'],
        [],
        ['Ученик', 'Email', 'Общий XP', 'Пройдено уровней',
         'Заданий всего', 'Сдано', 'Не сдано', 'Оценки (задание → оценка)'],
    ]
    for s in students:
        completed_levels = UserProgress.query.filter_by(
            user_id=s.id, status='completed').count()
        subs = {sub.assignment_id: sub for sub in
                Submission.query.filter(
                    Submission.student_id == s.id,
                    Submission.assignment_id.in_(assign_ids)
                ).all()} if assign_ids else {}
        submitted = len(subs)
        not_submitted = len(assign_ids) - submitted
        grades = '; '.join(
            f'{a.title} → {subs[a.id].grade or "нет оценки"}'
            for a in assignments if a.id in subs and subs[a.id].grade
        )
        rows.append([
            s.username, s.email, s.total_xp, completed_levels,
            len(assign_ids), submitted, not_submitted, grades,
        ])
    fname = f'group_{group.name}_{now_msk().strftime("%Y%m%d")}.csv'
    return _csv_response(rows, fname)


@app.route('/admin/export/all-students')
@login_required
@role_required('admin')
def admin_export_all_students():
    all_students = User.query.filter_by(role='student').order_by(User.username).all()
    groups = Group.query.all()

    now_str = now_msk().strftime('%d.%m.%Y %H:%M')
    rows = [
        [f'Все ученики платформы. Дата выгрузки: {now_str}'],
        [],
        ['Ученик', 'Email', 'Группы', 'Общий XP',
         'Пройдено уровней', 'Заданий сдано', 'Заданий не сдано'],
    ]
    # build maps: student_id → group names/ids
    student_group_names: dict = {}
    student_group_ids: dict = {}
    for g in groups:
        for m in g.members:
            student_group_names.setdefault(m.user_id, []).append(g.name)
            student_group_ids.setdefault(m.user_id, []).append(g.id)

    assign_by_group: dict = {}
    for a in Assignment.query.all():
        if a.group_id:
            assign_by_group.setdefault(a.group_id, []).append(a.id)

    # pre-fetch completed levels per student
    completed_map: dict = {}
    for row in db.session.query(
            UserProgress.user_id,
            db.func.count(UserProgress.id)
        ).filter_by(status='completed').group_by(UserProgress.user_id).all():
        completed_map[row[0]] = row[1]

    for s in all_students:
        grp_names = student_group_names.get(s.id, [])
        asgn_ids = []
        for gid in student_group_ids.get(s.id, []):
            asgn_ids.extend(assign_by_group.get(gid, []))
        asgn_ids = list(set(asgn_ids))
        submitted = (Submission.query
                     .filter(Submission.student_id == s.id,
                             Submission.assignment_id.in_(asgn_ids))
                     .count()) if asgn_ids else 0
        rows.append([
            s.username, s.email,
            ', '.join(grp_names) if grp_names else '—',
            s.total_xp,
            completed_map.get(s.id, 0),
            submitted,
            len(asgn_ids) - submitted,
        ])
    fname = f'all_students_{now_msk().strftime("%Y%m%d")}.csv'
    return _csv_response(rows, fname)


@app.route('/admin/export/teacher/<int:teacher_id>')
@login_required
@role_required('admin')
def admin_export_teacher(teacher_id):
    teacher = User.query.get_or_404(teacher_id)
    if teacher.role != 'teacher':
        return 'Not a teacher', 400
    assignments = Assignment.query.filter_by(teacher_id=teacher_id)\
        .order_by(Assignment.created_at.desc()).all()

    now_str = now_msk().strftime('%d.%m.%Y %H:%M')
    rows = [
        [f'Учитель: {teacher.username}'],
        [f'Email: {teacher.email}'],
        [f'Дата выгрузки: {now_str}'],
        [],
        ['=== ЗАДАНИЯ ==='],
        ['Задание', 'Группа', 'Создано', 'Дедлайн',
         'Всего работ', 'Проверено', 'Не проверено'],
    ]
    for a in assignments:
        grp = Group.query.get(a.group_id) if a.group_id else None
        total_subs = len(a.submissions)
        graded = sum(1 for s in a.submissions if s.grade)
        ungraded = total_subs - graded
        rows.append([
            a.title,
            grp.name if grp else '—',
            (a.created_at + timedelta(hours=3)).strftime('%d.%m.%Y') if a.created_at else '—',
            (a.due_date + timedelta(hours=3)).strftime('%d.%m.%Y') if a.due_date else '—',
            total_subs, graded, ungraded,
        ])

    rows += [
        [],
        ['=== РАБОТЫ УЧЕНИКОВ ==='],
        ['Задание', 'Ученик', 'Дата сдачи', 'Статус',
         'Оценка', 'Комментарий учителя'],
    ]
    for a in assignments:
        for sub in sorted(a.submissions, key=lambda x: x.submitted_at or datetime.min):
            student = User.query.get(sub.student_id)
            submitted_at = (sub.submitted_at + timedelta(hours=3)).strftime('%d.%m.%Y %H:%M') \
                if sub.submitted_at else '—'
            status_ru = {'submitted': 'Сдано', 'graded': 'Проверено',
                         'returned': 'Возвращено'}.get(sub.status, sub.status)
            rows.append([
                a.title,
                student.username if student else '—',
                submitted_at,
                status_ru,
                sub.grade or '—',
                sub.feedback or '—',
            ])

    fname = f'teacher_{teacher.username}_{now_msk().strftime("%Y%m%d")}.csv'
    return _csv_response(rows, fname)


# ── Admin backup ──────────────────────────────────────────────────────────────

@app.route('/admin/backup/create', methods=['POST'])
@login_required
@role_required('admin')
def admin_backup_create():
    try:
        name = create_backup('manual')
        return jsonify({'ok': True, 'name': name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/backup/list')
@login_required
@role_required('admin')
def admin_backup_list_api():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, 'backup_*.db')), reverse=True)
    result = []
    for f in files:
        stat = os.stat(f)
        name = os.path.basename(f)
        label = 'авто' if '_auto_' in name else 'вручную' if '_manual_' in name else 'пред.восст.' if '_pre-restore_' in name else ''
        result.append({
            'name': name,
            'size': stat.st_size,
            'mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%d.%m.%Y %H:%M'),
            'label': label,
        })
    return jsonify(result)


@app.route('/admin/backup/download/<path:filename>')
@login_required
@role_required('admin')
def admin_backup_download(filename):
    filename = os.path.basename(filename)
    path = os.path.join(BACKUP_DIR, filename)
    if not os.path.isfile(path):
        return 'Not found', 404
    with open(path, 'rb') as f:
        data = f.read()
    resp = make_response(data)
    resp.headers['Content-Type'] = 'application/octet-stream'
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


@app.route('/admin/backup/restore/<path:filename>', methods=['POST'])
@login_required
@role_required('admin')
def admin_backup_restore(filename):
    filename = os.path.basename(filename)
    src = os.path.join(BACKUP_DIR, filename)
    if not os.path.isfile(src):
        return jsonify({'error': 'Бекап не найден'}), 404
    try:
        create_backup('pre-restore')   # snapshot before overwrite
        db.engine.dispose()            # close all SQLAlchemy connections
        shutil.copy2(src, DB_PATH)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/backup/delete/<path:filename>', methods=['POST'])
@login_required
@role_required('admin')
def admin_backup_delete(filename):
    filename = os.path.basename(filename)
    path = os.path.join(BACKUP_DIR, filename)
    if not os.path.isfile(path):
        return jsonify({'error': 'Не найден'}), 404
    os.remove(path)
    return jsonify({'ok': True})


# ── Parent ────────────────────────────────────────────────────────────────────

@app.route('/parent/chat')
@login_required
@role_required('parent')
def parent_chat():
    children = User.query.filter_by(parent_id=current_user.id, role='student').all()
    teachers = []
    if children:
        child_ids = [c.id for c in children]
        memberships = GroupMember.query.filter(GroupMember.user_id.in_(child_ids)).all()
        g_ids = [m.group_id for m in memberships]
        if g_ids:
            groups = Group.query.filter(Group.id.in_(g_ids)).all()
            t_ids = {g.teacher_id for g in groups if g.teacher_id}
            teachers = User.query.filter(User.id.in_(t_ids)).all()
    admins = User.query.filter_by(role='admin').all()
    contacts = teachers + admins
    contact_id = request.args.get('with', type=int)
    messages = []
    if contact_id:
        messages = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == contact_id)) |
            ((Message.sender_id == contact_id) & (Message.receiver_id == current_user.id))
        ).order_by(Message.created_at).all()
        Message.query.filter_by(receiver_id=current_user.id, sender_id=contact_id, read=False)\
                     .update({'read': True})
        db.session.commit()
    unread_rows = db.session.query(Message.sender_id, db.func.count(Message.id))\
        .filter_by(receiver_id=current_user.id, read=False)\
        .group_by(Message.sender_id).all()
    unread_by_sender = {r[0]: r[1] for r in unread_rows}
    return render_template('parent/chat.html', contacts=contacts,
                           messages=messages, contact_id=contact_id,
                           unread_by_sender=unread_by_sender)


@app.route('/parent')
@login_required
@role_required('parent')
def parent_dashboard():
    children = User.query.filter_by(parent_id=current_user.id, role='student').all()
    child_data = []
    for child in children:
        memberships = GroupMember.query.filter_by(user_id=child.id).all()
        group_ids = [m.group_id for m in memberships]
        assignments = []
        if group_ids:
            assignments = Assignment.query.filter(
                Assignment.group_id.in_(group_ids)).order_by(
                Assignment.created_at.desc()).limit(5).all()
        subs = Submission.query.filter_by(student_id=child.id).all()
        notes = Note.query.filter_by(student_id=child.id).order_by(Note.created_at.desc()).limit(5).all()
        achievements = UserAchievement.query.filter_by(user_id=child.id).all()
        progress_count = UserProgress.query.filter_by(user_id=child.id, status='completed').count()
        child_data.append({
            'child': child,
            'assignments': assignments,
            'subs': subs,
            'notes': notes,
            'achievements': achievements,
            'progress_count': progress_count,
        })
    return render_template('parent/dashboard.html', child_data=child_data)


# ── API ───────────────────────────────────────────────────────────────────────

@app.route('/api/run-code', methods=['POST'])
@login_required
def api_run_code():
    code = request.json.get('code', '')
    stdin_data = request.json.get('stdin', '') or ''
    if len(code) > 5000:
        return jsonify({'error': 'Код слишком длинный'}), 400
    forbidden = ['import os', 'import sys', 'import subprocess', 'open(', '__import__',
                 'exec(', 'eval(', 'compile(', 'globals()', 'locals()', 'vars()',
                 'getattr(', 'setattr(', 'delattr(']
    for f in forbidden:
        if f in code:
            return jsonify({'error': f'Использование "{f}" запрещено в задачах'}), 400
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py',
                                         delete=False, encoding='utf-8') as tmp:
            tmp.write(code)
            tmp_path = tmp.name
        result = subprocess.run(
            ['python', '-X', 'utf8', tmp_path],
            capture_output=True, text=True, timeout=5, encoding='utf-8',
            errors='replace', input=stdin_data
        )
        os.unlink(tmp_path)
        return jsonify({
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        })
    except subprocess.TimeoutExpired:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return jsonify({'error': 'Превышено время выполнения (5 сек)'}), 408
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _is_trivial_code(code):
    """Return True if code is only print() calls with literal args — no real logic."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    if not tree.body:
        return False
    for node in tree.body:
        if not isinstance(node, ast.Expr):
            return False
        call = node.value
        if not isinstance(call, ast.Call):
            return False
        func = call.func
        if not (isinstance(func, ast.Name) and func.id == 'print'):
            return False
        for arg in call.args:
            if not isinstance(arg, ast.Constant):
                return False
        if call.keywords:
            return False
    return True


def _level_requires_logic(level):
    """True when the level needs real code, not just literal print() calls.

    Levels with only ["print"] in blocks_config are intro tasks where
    writing print("something") IS the correct solution — allow trivial code.
    Any level that also exposes var_set / if / for / while / def etc. requires
    actual logic, so trivial print-only code must be rejected.
    Code-only levels (empty blocks_config) also require real logic.
    """
    if not level.expected_output:
        return False
    if level.type == 'theory':
        return False
    try:
        raw = level.blocks_config or ''
        cfg = json.loads(raw) if raw else {}
        available = cfg.get('available', []) if isinstance(cfg, dict) else []
    except Exception:
        available = []
    # Only bare print blocks → task is literally "learn to use print()" → allow trivial
    if available and all(b == 'print' for b in available):
        return False
    # Any other block type present (var_set, if, for, while, def…)
    # OR no blocks at all (pure code level) → student must write real logic
    return True


@app.route('/api/complete-level', methods=['POST'])
@login_required
@role_required('student')
def api_complete_level():
    data = request.json
    level_id = data.get('level_id')
    code = data.get('code', '')
    level = Level.query.get_or_404(level_id)
    if code and _level_requires_logic(level) and _is_trivial_code(code):
        return jsonify({
            'error': 'trivial',
            'message': 'Попробуй решить задачу настоящим кодом! Просто вывести ответ через print() — не считается 😉'
        })
    progress = UserProgress.query.filter_by(
        user_id=current_user.id, level_id=level_id).first()
    if progress and progress.status == 'completed':
        return jsonify({'already_completed': True, 'xp': current_user.xp})
    if not progress:
        progress = UserProgress(user_id=current_user.id, level_id=level_id)
        db.session.add(progress)
    progress.status = 'completed'
    progress.completed_at = now_msk()
    current_user.xp += level.xp_reward
    current_user.total_xp += level.xp_reward
    # streak tracking
    today = now_msk().date()
    if current_user.last_activity_date != today:
        if current_user.last_activity_date == today - timedelta(days=1):
            current_user.streak = (current_user.streak or 0) + 1
        else:
            current_user.streak = 1
        current_user.last_activity_date = today
    # level up based on total earned XP
    while current_user.total_xp >= sum(i * 200 for i in range(1, current_user.level + 1)):
        current_user.level += 1
    db.session.commit()
    new_achievements = _check_achievements(current_user)
    return jsonify({
        'xp_gained': level.xp_reward,
        'total_xp': current_user.total_xp,
        'level': current_user.level,
        'new_achievements': [{'name': a.name, 'icon': a.icon} for a in new_achievements]
    })


def _grant_daily_login_bonus(user):
    today = now_msk().date()
    if user.last_login_bonus_date == today:
        return 0
    user.xp += DAILY_LOGIN_BONUS_XP
    user.total_xp += DAILY_LOGIN_BONUS_XP
    user.last_login_bonus_date = today
    db.session.commit()
    return DAILY_LOGIN_BONUS_XP


def _check_achievements(user):
    new = []
    all_ach = Achievement.query.all()
    owned_ids = {ua.achievement_id for ua in user.user_achievements}
    completed = UserProgress.query.filter_by(user_id=user.id, status='completed').count()
    for ach in all_ach:
        if ach.id in owned_ids:
            continue
        earned = False
        if ach.type == 'xp' and user.total_xp >= ach.threshold:
            earned = True
        elif ach.type == 'levels' and completed >= ach.threshold:
            earned = True
        if earned:
            db.session.add(UserAchievement(user_id=user.id, achievement_id=ach.id))
            new.append(ach)
    if new:
        db.session.commit()
    return new


@app.route('/api/set-difficulty', methods=['POST'])
@login_required
@role_required('student')
def api_set_difficulty():
    diff = request.json.get('difficulty', 'easy')
    if diff not in ('easy', 'hard'):
        return jsonify({'error': 'invalid'}), 400
    current_user.difficulty = diff
    db.session.commit()
    return jsonify({'difficulty': diff})


@app.route('/api/messages/unread-counts')
@login_required
def api_unread_counts():
    rows = db.session.query(Message.sender_id, db.func.count(Message.id))\
        .filter_by(receiver_id=current_user.id, read=False)\
        .group_by(Message.sender_id).all()
    return jsonify({str(r[0]): r[1] for r in rows})


@app.route('/api/messages', methods=['GET'])
@login_required
def api_get_messages():
    other_id = request.args.get('with', type=int)
    if not other_id:
        return jsonify([])
    msgs = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == other_id)) |
        ((Message.sender_id == other_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at).all()
    Message.query.filter_by(receiver_id=current_user.id, sender_id=other_id, read=False)\
                 .update({'read': True})
    db.session.commit()
    return jsonify([{
        'id': m.id,
        'sender_id': m.sender_id,
        'content': m.content,
        'created_at': utc_to_msk(m.created_at),
        'mine': m.sender_id == current_user.id
    } for m in msgs])


@app.route('/api/messages', methods=['POST'])
@login_required
def api_send_message():
    data = request.json
    receiver_id = data.get('receiver_id')
    content = data.get('content', '').strip()
    if not receiver_id or not content:
        return jsonify({'error': 'missing fields'}), 400
    msg = Message(sender_id=current_user.id, receiver_id=receiver_id, content=content)
    db.session.add(msg)
    db.session.commit()
    return jsonify({'id': msg.id, 'created_at': utc_to_msk(msg.created_at)})


@app.route('/api/buy-case', methods=['POST'])
@login_required
@role_required('student')
def api_buy_case():
    case_id = request.json.get('case_id')
    case = Case.query.get_or_404(case_id)
    if current_user.xp < case.price:
        return jsonify({'error': 'Недостаточно опыта!'}), 400
    # random avatar from case with rarity weights
    avatars = case.avatars
    if not avatars:
        return jsonify({'error': 'Кейс пуст'}), 400
    weights = {'common': 60, 'rare': 25, 'epic': 12, 'legendary': 3}
    w = [weights.get(av.rarity, 10) for av in avatars]
    won = random.choices(avatars, weights=w, k=1)[0]
    current_user.xp -= case.price
    already = UserAvatar.query.filter_by(user_id=current_user.id, avatar_id=won.id).first()
    duplicate_refund = 0
    if already:
        refund_table = {'common': 20, 'rare': 50, 'epic': 100, 'legendary': 200}
        duplicate_refund = refund_table.get(won.rarity, 20)
        current_user.xp += duplicate_refund
    else:
        db.session.add(UserAvatar(user_id=current_user.id, avatar_id=won.id))
    db.session.commit()
    return jsonify({
        'avatar': {'name': won.name, 'emoji': won.emoji, 'rarity': won.rarity},
        'remaining_xp': current_user.xp,
        'duplicate': bool(already),
        'refund_xp': duplicate_refund
    })


@app.route('/api/buy-avatar', methods=['POST'])
@login_required
@role_required('student')
def api_buy_avatar():
    avatar_id = request.json.get('avatar_id')
    avatar = Avatar.query.get_or_404(avatar_id)
    if current_user.xp < avatar.price:
        return jsonify({'error': 'Недостаточно опыта!'}), 400
    if UserAvatar.query.filter_by(user_id=current_user.id, avatar_id=avatar_id).first():
        return jsonify({'error': 'Уже куплено'}), 400
    current_user.xp -= avatar.price
    db.session.add(UserAvatar(user_id=current_user.id, avatar_id=avatar_id))
    db.session.commit()
    return jsonify({'remaining_xp': current_user.xp})


@app.route('/api/set-avatar', methods=['POST'])
@login_required
@role_required('student')
def api_set_avatar():
    avatar_id = request.json.get('avatar_id')
    ua = UserAvatar.query.filter_by(user_id=current_user.id, avatar_id=avatar_id).first()
    if not ua:
        return jsonify({'error': 'Аватар не куплен'}), 400
    UserAvatar.query.filter_by(user_id=current_user.id).update({'is_active': False})
    ua.is_active = True
    av = Avatar.query.get(avatar_id)
    current_user.avatar_emoji = av.emoji
    db.session.commit()
    return jsonify({'emoji': av.emoji})


@app.errorhandler(413)
def too_large(e):
    flash('Файл слишком большой. Максимальный размер — 16 МБ.', 'danger')
    return redirect(url_for('student_assignments'))


@app.route('/api/submit-assignment', methods=['POST'])
@login_required
@role_required('student')
def api_submit_assignment():
    assignment_id = request.form.get('assignment_id')
    content = request.form.get('content', '').strip()
    has_file = 'file' in request.files and request.files['file'].filename
    if not content and not has_file:
        flash('Нельзя отправить пустое задание — напиши ответ или прикрепи файл.', 'danger')
        return redirect(url_for('student_assignments'))
    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.is_closed:
        flash('Приём работ по этому заданию закрыт учителем.', 'danger')
        return redirect(url_for('student_assignments'))
    if assignment.due_date and now_msk() > assignment.due_date:
        flash('Срок сдачи истёк — приём работ закрыт автоматически.', 'danger')
        return redirect(url_for('student_assignments'))
    file_path = None
    if 'file' in request.files:
        f = request.files['file']
        if f.filename:
            if not allowed_file(f.filename):
                flash(
                    'Недопустимый тип файла. Разрешены: PDF, DOC, DOCX, TXT, PY, '
                    'JPG, PNG, GIF, ZIP, XLS, XLSX, PPT, PPTX.',
                    'danger'
                )
                return redirect(url_for('student_assignments'))
            filename = secure_filename(f.filename)
            fpath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            f.save(fpath)
            file_path = filename
    existing = Submission.query.filter_by(
        assignment_id=assignment_id, student_id=current_user.id).first()
    if existing:
        existing.content = content
        existing.file_path = file_path
        existing.submitted_at = datetime.utcnow()
        existing.status = 'submitted'
    else:
        sub = Submission(assignment_id=assignment_id, student_id=current_user.id,
                         content=content, file_path=file_path)
        db.session.add(sub)
    db.session.commit()
    flash('Задание отправлено!', 'success')
    return redirect(url_for('student_assignments'))


_ETHICS_SEED = [
    ('🎨', 'Зачем писать красиво?', '''<p>Представь: ты написал программу, а потом заболел на две недели. Когда ты вернулся — сам не можешь понять, что там написано! Это случается с каждым программистом, если он не думает о чистоте кода.</p>
<p>Чистый код — это код, который <strong>легко читать и понимать</strong>. Его пишут не только для компьютера, но и для людей — для себя завтра и для других программистов.</p>
<pre><code># Плохой вариант — непонятно ничего
x=int(input())
y=x*24*60
print(y)

# Хороший вариант — сразу понятно что происходит
hours = int(input())
minutes = hours * 24 * 60
print(minutes)</code></pre>
<ul>
<li><code>x</code>, <code>y</code> — что это? Непонятно без долгого изучения.</li>
<li><code>hours</code>, <code>minutes</code> — всё понятно с первого взгляда!</li>
</ul>
<p>Говорят, что код читают в 10 раз чаще, чем пишут. Значит, на читаемость стоит тратить время!</p>
<div class="tip">💡 Правило хорошего программиста: пиши код так, как будто его прочитает твой друг — без объяснений!</div>''', 0),

    ('🏷️', 'Правила имён переменных', '''<p>Имя переменной — это как ярлычок на коробке. Если написать «Штука» — непонятно что внутри. В Python есть общепринятые правила имён — <strong>PEP 8</strong>.</p>
<pre><code># Переменные — snake_case (слова через подчёркивание)
user_name = "Петя"          # ✅ правильно
userName = "Петя"           # ❌ не принято в Python

# Имена должны говорить что хранится
a = 15                      # ❌ что такое a?
student_age = 15            # ✅ сразу понятно

# Функции — глагол + что делает
def calculate_area(): ...   # ✅
def ca(): ...               # ❌ непонятная аббревиатура

# Константы — ЗАГЛАВНЫМИ БУКВАМИ
MAX_SPEED = 120             # ✅</code></pre>
<ul>
<li><strong>snake_case</strong>: слова разделяются подчёркиванием — <code>my_variable</code></li>
<li><strong>Говорящие имена</strong>: <code>user_score</code> лучше чем <code>us</code> или <code>x</code></li>
<li><strong>Не сокращай без нужды</strong>: <code>temperature</code> лучше чем <code>temp</code></li>
</ul>
<div class="tip">💡 Тест хорошего имени: прочитай его вслух — сразу понятно что хранится в переменной? Если нет — придумай другое!</div>''', 1),

    ('📐', 'Отступы и форматирование', '''<p>В Python отступы — это часть синтаксиса! Без правильных отступов код не запустится. По стандарту PEP 8 используй <strong>4 пробела</strong> на каждый уровень вложенности.</p>
<pre><code># ❌ Плохо — один пробел, трудно читать
def check_age(age):
 if age>=18:
  print("Взрослый")

# ✅ Хорошо — 4 пробела, видна структура
def check_age(age):
    if age >= 18:
        print("Взрослый")
    else:
        print("Ребёнок")</code></pre>
<ul>
<li>Всегда <strong>4 пробела</strong> (в нашем редакторе Tab = 4 пробела автоматически)</li>
<li>Между функциями — 2 пустые строки</li>
<li>После запятой — пробел: <code>print(a, b)</code></li>
<li>Вокруг операторов — пробелы: <code>x = a + b</code>, а не <code>x=a+b</code></li>
</ul>
<pre><code># ❌ Без пробелов — глаза болят
result=price*quantity+tax

# ✅ С пробелами — сразу видна структура
result = price * quantity + tax</code></pre>
<div class="tip">💡 Клавиша Tab в редакторе вставляет ровно 4 пробела — используй её!</div>''', 2),

    ('📝', 'Зачем нужны комментарии?', '''<p>Комментарий — это текст в коде, который Python <em>игнорирует</em>. Он написан для людей! Комментарии объясняют <strong>почему</strong> написан именно такой код.</p>
<pre><code># Это однострочный комментарий

result = price * 0.9  # скидка 10% для постоянных клиентов

def calculate_discount(price, percent):
    """Считает цену со скидкой. Возвращает новую цену."""
    return price * (1 - percent / 100)</code></pre>
<p><strong>Когда комментарий нужен:</strong></p>
<ul>
<li>Когда код делает что-то неочевидное: <code># умножаем на 1.2 потому что НДС 20%</code></li>
<li>В начале каждой функции — что она делает</li>
<li>Когда объясняешь необычный алгоритм</li>
</ul>
<p><strong>Когда комментарий лишний:</strong></p>
<ul>
<li><code>x = x + 1  # увеличиваем x на 1</code> — это и так видно из кода!</li>
<li>Дублировать то, что уже сказано именем переменной</li>
</ul>
<div class="tip">💡 Хороший код объясняет КАК, хороший комментарий объясняет ПОЧЕМУ. Если комментарий говорит «делает X» — лучше просто назови переменную X!</div>''', 3),

    ('🤝', 'Чужой код — не твой', '''<p>В программировании, как и в жизни, важно быть честным. Если взял чужой код — нужно это указать. Многие программисты делятся кодом бесплатно — это называется <em>Open Source</em>.</p>
<pre><code># Если использовал чужую функцию — напиши об этом!
# Источник: Stack Overflow (https://stackoverflow.com/...)
def flatten_list(nested):
    return [item for sublist in nested for item in sublist]

# Дальше — твой собственный код
my_list = [[1, 2], [3, 4], [5]]
print(flatten_list(my_list))  # [1, 2, 3, 4, 5]</code></pre>
<p><strong>Правила честного программиста:</strong></p>
<ul>
<li>🔗 <strong>Указывай источник</strong> — ссылку в комментарии</li>
<li>✍️ <strong>Понимай код</strong> который копируешь — иначе не научишься</li>
<li>🚫 <strong>Не сдавай чужое как своё</strong> — это плагиат</li>
<li>📚 <strong>Учись на чужом коде</strong> — читай как другие решают задачи</li>
</ul>
<div class="tip">💡 Скопировал → прочитал каждую строку → понял → переписал сам. Вот правильный способ учиться на чужом коде!</div>''', 4),

    ('👥', 'Будь добрым в команде', '''<p>Большинство программ написаны командами. Умение работать с людьми — не менее важный навык, чем знание Python!</p>
<p><strong>Code Review</strong> — это когда другой программист читает твой код и даёт советы. Это нормально, не обижайся!</p>
<pre><code># Как НЕ надо комментировать чужой код:
# "Это полный бред, кто так пишет???"   ← грубо

# Как надо — конкретно и уважительно:
# "Здесь можно использовать list comprehension:
#  result = [x*2 for x in numbers]
#  Как думаешь?"</code></pre>
<ul>
<li>💬 <strong>Критикуй код, а не человека</strong> — «этот подход медленный» вместо «ты написал плохо»</li>
<li>🙏 <strong>Принимай критику спокойно</strong> — свежий взгляд очень ценен</li>
<li>✅ <strong>Хвали хорошие решения</strong> — «отличная идея!» тоже часть работы</li>
<li>📖 <strong>Пиши документацию</strong> — коллегам не нужно гадать как пользоваться кодом</li>
</ul>
<div class="tip">💡 Помни: все когда-то были новичками. Помогай тем, кто только начинает — объясняя другим, сам лучше понимаешь!</div>''', 5),

    ('🔒', 'Защита данных пользователей', '''<p>Когда люди пользуются программой — они доверяют тебе свои данные: имя, пароль, адрес. Это огромная ответственность!</p>
<pre><code># ❌ НИКОГДА так — пароль виден всем!
users = {"petya": "password123"}

# ✅ Правильно — хешируем пароль
import hashlib
password = "password123"
safe_password = hashlib.sha256(password.encode()).hexdigest()
# Хранится: "ef92b7..." — угадать исходный пароль невозможно</code></pre>
<p><strong>Что нельзя делать с данными пользователей:</strong></p>
<ul>
<li>🚫 Хранить пароли в открытом виде (только зашифрованными!)</li>
<li>🚫 Передавать данные посторонним без разрешения</li>
<li>🚫 Собирать данные которые не нужны программе</li>
<li>🚫 Оставлять личные данные в логах</li>
</ul>
<p><strong>Принцип минимума данных:</strong> собирай только то, что реально нужно. Если приложение — калькулятор, зачем ему адрес пользователя?</p>
<div class="tip">💡 Золотое правило: обращайся с данными пользователей так, как хотел бы чтобы обращались с твоими. Уважай чужую приватность!</div>''', 6),
]


def _seed_library_articles():
    for icon, title, content, order in _ETHICS_SEED:
        db.session.add(LibraryArticle(
            icon=icon, title=title, content=content,
            category='Этика кода', order=order, has_sandbox=True,
        ))
    db.session.commit()


@app.route('/admin/library')
@login_required
@role_required('admin')
def admin_library():
    articles = LibraryArticle.query.order_by(LibraryArticle.category, LibraryArticle.order).all()
    categories = {}
    for a in articles:
        categories.setdefault(a.category, []).append(a)
    return render_template('admin/library.html', articles=articles, categories=categories)


@app.route('/admin/library/add', methods=['POST'])
@login_required
@role_required('admin')
def admin_library_add():
    title = request.form.get('title', '').strip()
    if not title:
        flash('Название обязательно', 'danger')
        return redirect(url_for('admin_library'))
    article = LibraryArticle(
        title=title,
        content=request.form.get('content', ''),
        icon=request.form.get('icon', '📄').strip() or '📄',
        category=request.form.get('category', '').strip() or 'Общее',
        order=int(request.form.get('order', 0) or 0),
        has_sandbox='has_sandbox' in request.form,
    )
    db.session.add(article)
    db.session.commit()
    flash('Статья добавлена!', 'success')
    return redirect(url_for('admin_library'))


@app.route('/admin/library/<int:article_id>/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_library_edit(article_id):
    article = LibraryArticle.query.get_or_404(article_id)
    article.title = request.form.get('title', article.title).strip() or article.title
    article.content = request.form.get('content', article.content)
    article.icon = request.form.get('icon', article.icon).strip() or article.icon
    article.category = request.form.get('category', article.category).strip() or article.category
    article.order = int(request.form.get('order', article.order) or article.order)
    article.has_sandbox = 'has_sandbox' in request.form
    db.session.commit()
    flash('Статья обновлена!', 'success')
    return redirect(url_for('admin_library'))


@app.route('/admin/library/<int:article_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_library_delete(article_id):
    article = LibraryArticle.query.get_or_404(article_id)
    db.session.delete(article)
    db.session.commit()
    flash('Статья удалена', 'success')
    return redirect(url_for('admin_library'))


def _migrate_db():
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    user_cols = {c['name'] for c in inspector.get_columns('user')}
    with db.engine.connect() as conn:
        if 'streak' not in user_cols:
            conn.execute(text('ALTER TABLE user ADD COLUMN streak INTEGER DEFAULT 0'))
        if 'last_activity_date' not in user_cols:
            conn.execute(text('ALTER TABLE user ADD COLUMN last_activity_date DATE'))
        if 'last_login_bonus_date' not in user_cols:
            conn.execute(text('ALTER TABLE user ADD COLUMN last_login_bonus_date DATE'))
        if 'total_xp' not in user_cols:
            conn.execute(text('ALTER TABLE user ADD COLUMN total_xp INTEGER DEFAULT 0'))
            conn.execute(text('UPDATE user SET total_xp = xp WHERE role = \'student\''))
        assign_cols = {c['name'] for c in inspector.get_columns('assignment')}
        if 'is_closed' not in assign_cols:
            conn.execute(text('ALTER TABLE assignment ADD COLUMN is_closed BOOLEAN DEFAULT 0'))
        conn.commit()
    # Seed ethics articles if table is empty
    if LibraryArticle.query.count() == 0:
        _seed_library_articles()


with app.app_context():
    db.create_all()
    _migrate_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
