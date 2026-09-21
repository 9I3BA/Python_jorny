"""Add 4 bonus challenge modules with real code-only levels (140 XP each).
Run once: python add_bonus_levels.py
"""
from sqlalchemy import text
from app import app, db
from models import Module, Level

XP = 140  # 2x standard hard level


def H(title, task, expected, hint, order):
    return Level(
        title=title, type='hard', xp_reward=XP,
        theory_content='',
        task_description=task,
        expected_output=expected,
        blocks_config='{}',
        hint=hint,
        order=order,
    )


BONUS_MODULES = [
    # ─── BONUS 1 ─ after modules 1-4 (print, variables, booleans, if/else) ────
    {
        'title': 'Испытание: Начало пути',
        'icon': '⭐',
        'color': '#FFD700',
        'description': 'Бонусные задачи по темам: вывод, переменные, булевы значения и условия',
        'order': 100,
        'levels': [
            H(
                'Больший из двух',
                'a=17, b=29. Если a больше b — выведи a, иначе выведи b.',
                '29',
                'a = 17\nb = 29\nif a > b:\n    print(a)\nelse:\n    print(b)',
                1,
            ),
            H(
                'Чётность и знак',
                'n=14. Выведи "Чётное" если n%2==0, иначе "Нечётное".\nЗатем на следующей строке выведи "Положительное" если n>0, иначе "Отрицательное".',
                'Чётное\nПоложительное',
                'n = 14\nif n % 2 == 0:\n    print("Чётное")\nelse:\n    print("Нечётное")\nif n > 0:\n    print("Положительное")\nelse:\n    print("Отрицательное")',
                2,
            ),
            H(
                'Калькулятор скидки',
                'price=3000, discount_pct=20.\nВычисли: final = price - price * discount_pct // 100\nВыведи: Итого: {final} руб.',
                'Итого: 2400 руб.',
                'price = 3000\ndiscount_pct = 20\nfinal = price - price * discount_pct // 100\nprint(f"Итого: {final} руб.")',
                3,
            ),
            H(
                'Категория скорости',
                'speed=95.\nЕсли speed < 60 — "Медленно",\nelif speed < 100 — "Нормально",\nelif speed < 150 — "Быстро",\nиначе — "Опасно".',
                'Нормально',
                'speed = 95\nif speed < 60:\n    print("Медленно")\nelif speed < 100:\n    print("Нормально")\nelif speed < 150:\n    print("Быстро")\nelse:\n    print("Опасно")',
                4,
            ),
            H(
                'Индекс массы тела',
                'weight=70, height=175.\nbmi = round(weight / (height / 100) ** 2)\nВыведи f"ИМТ: {bmi}".\nЗатем: если bmi<18 — "Недостаток веса", bmi<25 — "Норма", иначе — "Избыток".',
                'ИМТ: 23\nНорма',
                'weight = 70\nheight = 175\nbmi = round(weight / (height / 100) ** 2)\nprint(f"ИМТ: {bmi}")\nif bmi < 18:\n    print("Недостаток веса")\nelif bmi < 25:\n    print("Норма")\nelse:\n    print("Избыток")',
                5,
            ),
        ],
    },
    # ─── BONUS 2 ─ after modules 5-8 (elif/and/or, for, while, functions) ──────
    {
        'title': 'Испытание: Исследователь',
        'icon': '⭐',
        'color': '#FF9500',
        'description': 'Бонусные задачи по темам: elif, циклы for и while, функции',
        'order': 200,
        'levels': [
            H(
                'Сумма цикла',
                'Используя цикл for и переменную total=0, посчитай сумму чисел от 1 до 10.\nВыведи результат.',
                '55',
                'total = 0\nfor i in range(1, 11):\n    total += i\nprint(total)',
                1,
            ),
            H(
                'FizzBuzz',
                'Для чисел от 1 до 10:\n- если делится на 3 и 5 — "FizzBuzz"\n- если на 3 — "Fizz"\n- если на 5 — "Buzz"\n- иначе само число',
                '1\n2\nFizz\n4\nBuzz\nFizz\n7\n8\nFizz\nBuzz',
                'for i in range(1, 11):\n    if i % 3 == 0 and i % 5 == 0:\n        print("FizzBuzz")\n    elif i % 3 == 0:\n        print("Fizz")\n    elif i % 5 == 0:\n        print("Buzz")\n    else:\n        print(i)',
                2,
            ),
            H(
                'Факториал',
                'Напиши функцию factorial(n), которая считает n! с помощью цикла while.\nВызови factorial(5) и выведи результат.',
                '120',
                'def factorial(n):\n    result = 1\n    i = 1\n    while i <= n:\n        result *= i\n        i += 1\n    return result\nprint(factorial(5))',
                3,
            ),
            H(
                'Простые числа до 20',
                'Напиши функцию is_prime(n): возвращает True если n простое, иначе False.\nВыведи все простые числа от 2 до 19.',
                '2\n3\n5\n7\n11\n13\n17\n19',
                'def is_prime(n):\n    if n < 2:\n        return False\n    for i in range(2, n):\n        if n % i == 0:\n            return False\n    return True\nfor i in range(2, 20):\n    if is_prime(i):\n        print(i)',
                4,
            ),
            H(
                'Сумма квадратов',
                'Напиши функцию sum_squares(n), которая возвращает сумму квадратов чисел от 1 до n.\nВыведи sum_squares(4).',
                '30',
                'def sum_squares(n):\n    total = 0\n    for i in range(1, n + 1):\n        total += i * i\n    return total\nprint(sum_squares(4))',
                5,
            ),
        ],
    },
    # ─── BONUS 3 ─ after modules 9-12 (lists, dicts, strings, math) ────────────
    {
        'title': 'Испытание: Мастер',
        'icon': '⭐',
        'color': '#FF6600',
        'description': 'Бонусные задачи по темам: списки, словари, методы строк, математика',
        'order': 300,
        'levels': [
            H(
                'Максимум вручную',
                'nums=[5, 3, 8, 2, 9, 1].\nНайди максимальный элемент через цикл (без max()).\nВыведи его.',
                '9',
                'nums = [5, 3, 8, 2, 9, 1]\nmax_val = nums[0]\nfor n in nums:\n    if n > max_val:\n        max_val = n\nprint(max_val)',
                1,
            ),
            H(
                'Подсчёт символа',
                'text="mississippi".\nПодсчитай сколько раз встречается буква "s" через цикл.\nВыведи результат.',
                '4',
                'text = "mississippi"\ncount = 0\nfor c in text:\n    if c == "s":\n        count += 1\nprint(count)',
                2,
            ),
            H(
                'Слова в верхнем регистре',
                'words=["python", "java", "c++"].\nДля каждого слова выведи его в верхнем регистре.',
                'PYTHON\nJAVA\nC++',
                'words = ["python", "java", "c++"]\nfor w in words:\n    print(w.upper())',
                3,
            ),
            H(
                'Статистика списка',
                'nums=[4, 2, 8, 6, 10].\nВыведи одной строкой: f"Сумма: {sum}, Макс: {max}, Мин: {min}"',
                'Сумма: 30, Макс: 10, Мин: 2',
                'nums = [4, 2, 8, 6, 10]\nprint(f"Сумма: {sum(nums)}, Макс: {max(nums)}, Мин: {min(nums)}")',
                4,
            ),
            H(
                'Фильтрация чётных',
                'nums=[1,2,3,4,5,6,7,8,9,10].\nСоздай список result из чётных чисел больше 5.\nВыведи каждый элемент.',
                '6\n8\n10',
                'nums = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]\nresult = []\nfor n in nums:\n    if n % 2 == 0 and n > 5:\n        result.append(n)\nfor n in result:\n    print(n)',
                5,
            ),
        ],
    },
    # ─── BONUS 4 ─ after modules 13-16 (f-strings, nested, master, ethics) ─────
    {
        'title': 'Испытание: Эксперт',
        'icon': '⭐',
        'color': '#BC8CFF',
        'description': 'Бонусные задачи по темам: f-строки, вложенные конструкции, комплексные задачи',
        'order': 400,
        'levels': [
            H(
                'Таблица умножения',
                'Выведи таблицу умножения от 1 до 3 в формате "i x j = результат".\n(i от 1 до 3, j от 1 до 3)',
                '1 x 1 = 1\n1 x 2 = 2\n1 x 3 = 3\n2 x 1 = 2\n2 x 2 = 4\n2 x 3 = 6\n3 x 1 = 3\n3 x 2 = 6\n3 x 3 = 9',
                'for i in range(1, 4):\n    for j in range(1, 4):\n        print(f"{i} x {j} = {i * j}")',
                1,
            ),
            H(
                'Числовой треугольник',
                'Выведи треугольник из цифр (4 строки):\nСтрока 1: "1"\nСтрока 2: "12"\nСтрока 3: "123"\nСтрока 4: "1234"',
                '1\n12\n123\n1234',
                'for i in range(1, 5):\n    s = ""\n    for j in range(1, i + 1):\n        s += str(j)\n    print(s)',
                2,
            ),
            H(
                'Анализатор текста',
                'text="Hello World Python".\nВыведи три строки:\n1) количество слов\n2) первое слово в ВЕРХНЕМ регистре\n3) последнее слово в нижнем регистре',
                '3\nHELLO\npython',
                'text = "Hello World Python"\nwords = text.split()\nprint(len(words))\nprint(words[0].upper())\nprint(words[-1].lower())',
                3,
            ),
            H(
                'Пирамида звёздочек',
                'Выведи пирамиду из * высотой 4 строки:\nСтрока 1: *\nСтрока 2: **\nСтрока 3: ***\nСтрока 4: ****',
                '*\n**\n***\n****',
                'for i in range(1, 5):\n    print("*" * i)',
                4,
            ),
            H(
                'Шифр Цезаря',
                'message="abc".\nДля каждого символа c в message выведи chr(ord(c) + 1)\n(каждый символ на новой строке).',
                'b\nc\nd',
                'message = "abc"\nfor c in message:\n    print(chr(ord(c) + 1))',
                5,
            ),
        ],
    },
]


def run():
    with app.app_context():
        # ── 1. Add is_bonus column if missing ───────────────────────────────
        try:
            db.session.execute(text('ALTER TABLE module ADD COLUMN is_bonus BOOLEAN DEFAULT 0'))
            db.session.commit()
            print('Added is_bonus column.')
        except Exception:
            db.session.rollback()
            print('is_bonus column already exists.')

        # ── 2. Remove old bonus modules (idempotent re-run) ─────────────────
        existing = db.session.execute(
            text("SELECT id FROM module WHERE is_bonus = 1")
        ).fetchall()
        for row in existing:
            mid = row[0]
            db.session.execute(
                text("DELETE FROM user_progress WHERE level_id IN "
                     "(SELECT id FROM level WHERE module_id = :mid)"), {'mid': mid})
            db.session.execute(text("DELETE FROM level WHERE module_id = :mid"), {'mid': mid})
            db.session.execute(text("DELETE FROM module WHERE id = :mid"), {'mid': mid})
        db.session.commit()

        # ── 3. Insert bonus modules + levels ────────────────────────────────
        for bm_data in BONUS_MODULES:
            levels_data = bm_data.pop('levels')
            bm = Module(
                title=bm_data['title'],
                icon=bm_data['icon'],
                color=bm_data['color'],
                description=bm_data['description'],
                order=bm_data['order'],
                is_bonus=True,
                map_x=0, map_y=0,
            )
            db.session.add(bm)
            db.session.flush()  # get bm.id

            for lv in levels_data:
                lv.module_id = bm.id
                db.session.add(lv)

        db.session.commit()
        print('Bonus modules created:')
        for bm in Module.query.filter_by(is_bonus=True).order_by(Module.order).all():
            count = Level.query.filter_by(module_id=bm.id).count()
            print(f'  [{bm.id}] {bm.title} — {count} levels × {XP} XP')


if __name__ == '__main__':
    run()
