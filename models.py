from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, teacher, student, parent
    xp = db.Column(db.Integer, default=0)
    total_xp = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    avatar_emoji = db.Column(db.String(10), default='🐱')
    difficulty = db.Column(db.String(10), default='easy')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    parent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    streak = db.Column(db.Integer, default=0)
    last_activity_date = db.Column(db.Date, nullable=True)
    last_login_bonus_date = db.Column(db.Date, nullable=True)

    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)
    user_progress = db.relationship('UserProgress', backref='user', lazy=True)
    user_achievements = db.relationship('UserAchievement', backref='user', lazy=True)
    user_avatars = db.relationship('UserAvatar', backref='user', lazy=True)
    submissions = db.relationship('Submission', foreign_keys='Submission.student_id', backref='student', lazy=True)

    def xp_to_next_level(self):
        return self.level * 200

    def level_progress_pct(self):
        xp_in_level = self.total_xp - sum(i * 200 for i in range(1, self.level))
        return min(100, int(xp_in_level / self.xp_to_next_level() * 100))


class Module(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    order = db.Column(db.Integer, default=0)
    icon = db.Column(db.String(10), default='🏴‍☠️')
    color = db.Column(db.String(20), default='#4ecdc4')
    map_x = db.Column(db.Integer, default=0)
    map_y = db.Column(db.Integer, default=0)
    is_bonus = db.Column(db.Boolean, default=False)

    levels = db.relationship('Level', backref='module', lazy=True, order_by='Level.order')


class Level(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey('module.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), default='blocks')  # theory, blocks
    order = db.Column(db.Integer, default=0)
    xp_reward = db.Column(db.Integer, default=50)
    theory_content = db.Column(db.Text)
    task_description = db.Column(db.Text)
    expected_output = db.Column(db.String(500))
    blocks_config = db.Column(db.Text)
    hint = db.Column(db.Text)

    progress = db.relationship('UserProgress', backref='level', lazy=True)


class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    level_id = db.Column(db.Integer, db.ForeignKey('level.id'), nullable=False)
    status = db.Column(db.String(20), default='not_started')
    completed_at = db.Column(db.DateTime)


class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    members = db.relationship('GroupMember', backref='group', lazy=True)
    assignments = db.relationship('Assignment', backref='group', lazy=True)


class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    due_date = db.Column(db.DateTime)
    is_closed = db.Column(db.Boolean, default=False)
    file_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    submissions = db.relationship('Submission', backref='assignment', lazy=True)
    teacher = db.relationship('User', foreign_keys=[teacher_id])


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text)
    file_path = db.Column(db.String(255))
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    grade = db.Column(db.String(10))
    feedback = db.Column(db.Text)
    status = db.Column(db.String(20), default='submitted')


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)


class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(10), default='🏆')
    type = db.Column(db.String(50))
    threshold = db.Column(db.Integer, default=0)


class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id'), nullable=False)
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)

    achievement = db.relationship('Achievement')


class Avatar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    emoji = db.Column(db.String(10), default='🐍')
    price = db.Column(db.Integer, default=100)
    rarity = db.Column(db.String(20), default='common')
    case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=True)


class Case(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Integer, default=200)
    emoji = db.Column(db.String(10), default='📦')
    color = db.Column(db.String(20), default='#6c5ce7')

    avatars = db.relationship('Avatar', backref='case', lazy=True)


class UserAvatar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    avatar_id = db.Column(db.Integer, db.ForeignKey('avatar.id'), nullable=False)
    purchased_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=False)

    avatar = db.relationship('Avatar')


class LibraryArticle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, default='')
    icon = db.Column(db.String(10), default='📄')
    category = db.Column(db.String(100), default='Общее')
    order = db.Column(db.Integer, default=0)
    has_sandbox = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), default='remark')  # remark, achievement
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('User', foreign_keys=[student_id])
    teacher_user = db.relationship('User', foreign_keys=[teacher_id])
