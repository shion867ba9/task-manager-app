from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dateutil.parser import parse as parse_dt
from datetime import datetime, timezone, timedelta
import os
import json
import glob

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, "db", "app.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////home/shion867ba9/project/taskmanaging_app/main/db/app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

TASK_STATUS_CHOICES = [
    '未着手', '進行中', '完了', '保留', '棚上げ', '割込み', 'MTG', 'フリーログ'
]
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')

PROJECT_COLORS = [
    "#FFB3BA",  # パステルレッド（薄いサーモンピンク）
    "#FFDFBA",  # パステルオレンジ（アプリコット）
    "#FFFFBA",  # パステルイエロー（クリームイエロー）
    "#BAFFC9",  # パステルグリーン（ミントグリーン）
    "#BAE1FF",  # パステルブルー（ベビーブルー）
    "#D5BAFF",  # パステルパープル（ラベンダー）
    "#FFE1FF",  # パステルピンク（ピンク・ラベンダー）
    "#E2F0CB",  # パステルライムグリーン（ごく淡い黄緑）
]
DEFAULT_COLOR = "#888888"  # 未割当


# モデル定義（models.pyに分離も可）
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    theme_id = db.Column(db.Integer, db.ForeignKey('theme.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    title = db.Column(db.String(100), nullable=False)
    detail = db.Column(db.String(1000))
    scheduled_start = db.Column(db.DateTime)
    scheduled_end = db.Column(db.DateTime)
    weight = db.Column(db.Integer, default=10)
    status = db.Column(db.String(20), default='未着手')
    @property
    def is_completed(self):
        return TaskWorkLog.query.filter_by(task_id=self.id).first() is not None
    # 追加: 子テーブルとして実績を持つ
    worklogs = db.relationship('TaskWorkLog', backref='task', lazy=True)

    parent_task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    subtasks = db.relationship('Task', backref=db.backref('parent_task', remote_side=[id]), lazy=True)
    # リレーションシップの追加
    project = db.relationship('Project', backref=db.backref('tasks', lazy=True))
    theme = db.relationship('Theme', backref=db.backref('tasks', lazy=True))


class TaskWorkLog(db.Model):  # タスクの作業実績
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'))
    work_date = db.Column(db.Date)  # 作業日
    start_at = db.Column(db.DateTime)  # 実作業開始日時
    end_at = db.Column(db.DateTime)    # 実作業終了日時
    work_time = db.Column(db.Float)    # 工数（時間など）
    status = db.Column(db.String(20), default='実績')   # ←追加
    memo = db.Column(db.String(500))   # 備考（任意）
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    theme_id = db.Column(db.Integer, db.ForeignKey('theme.id'), nullable=True)
    is_pinned = db.Column(db.Boolean, default=False)  # ★追加

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    description = db.Column(db.String(500))
    progress = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='未着手')
    scheduled_start = db.Column(db.Date)
    scheduled_end = db.Column(db.Date)
    start_date_actual = db.Column(db.Date)
    end_date_actual = db.Column(db.Date)
    label = db.Column(db.String(100))
    color = db.Column(db.String(7), default=None)  # HEX "#AABBCC"

class Theme(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    name = db.Column(db.String(100))
    description = db.Column(db.String(500))
    detail = db.Column(db.String(1000))
    progress = db.Column(db.Integer, default=0)
    scheduled_start = db.Column(db.DateTime)
    scheduled_end = db.Column(db.DateTime)
    duration_plan = db.Column(db.Float)
    start_dt_actual = db.Column(db.DateTime)
    end_dt_actual = db.Column(db.DateTime)
    duration_actual = db.Column(db.Float)
    status = db.Column(db.String(20), default='未着手')
    label = db.Column(db.String(100))
    project = db.relationship('Project', backref=db.backref('themes', lazy=True))


class UndoRedoLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action_type = db.Column(db.String(20))
    target_table = db.Column(db.String(50))
    target_id = db.Column(db.Integer)
    data_before = db.Column(db.Text)
    data_after = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    undo_group = db.Column(db.String(50), nullable=True)
    undone = db.Column(db.Boolean, default=False)


class WorkLogFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    worklog_id = db.Column(db.Integer, db.ForeignKey('task_work_log.id'), nullable=False)
    filename = db.Column(db.String(255))
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)


@app.route('/')
def index():
    return redirect(url_for('calendar_view'))

@app.route('/calendar')
def calendar_view():
    projects = Project.query.order_by(Project.name).all()
    themes = Theme.query.order_by(Theme.name).all()
    return render_template('calendar.html', projects=projects, themes=themes)

def darken_color(hex_color, factor=0.5):
    # HEX→RGB→HSL処理で50%暗く
    import colorsys
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r/255., g/255., b/255.)
    l = max(0, l * factor)
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return '#{:02x}{:02x}{:02x}'.format(int(r2*255), int(g2*255), int(b2*255))

# タスクAPI（FullCalendar連携用JSON）
@app.route('/api/tasks')
def api_tasks():
    tasks = Task.query.all()
    events = []
    for t in tasks:
        # 1つでも該当作業実績があれば1つだけ取得
        worklog = TaskWorkLog.query.filter_by(task_id=t.id).first()
        pj = Project.query.get(t.project_id) if t.project_id else None
        color = pj.color if pj and pj.color else "#d3d3d3"
        if t.is_completed:
            color = darken_color(color, 0.5)
        events.append({
            'id': t.id,
            'title': t.title,
            'start': t.scheduled_start.isoformat() if t.scheduled_start else None,
            'end': t.scheduled_end.isoformat() if t.scheduled_end else None,
            'color': color,
            'is_completed': bool(worklogs),  # 作業実績が1つでもあればTrue
            'worklog_id': worklog.id if worklog else None,
        })
    return jsonify(events)



# 2 プロジェクト一覧
# 一覧画面ルート
@app.route('/projects')
def list_projects():
    projects = Project.query.all()
    return render_template('project_list.html', projects=projects)



def assign_project_color():
    count = Project.query.count()
    return PROJECT_COLORS[count % len(PROJECT_COLORS)]

@app.route('/project/new', methods=['GET', 'POST'])
def new_project():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        progress = int(request.form.get('progress', 0))
        status = request.form['status']
        scheduled_start_raw = request.form.get('scheduled_start') or None
        scheduled_end_raw = request.form.get('scheduled_end') or None
        scheduled_start = datetime.strptime(scheduled_start_raw, "%Y-%m-%d").date() if scheduled_start_raw else None
        scheduled_end = datetime.strptime(scheduled_end_raw, "%Y-%m-%d").date() if scheduled_end_raw else None

        # ここで色を割り当てる
        color = assign_project_color()
        pj = Project(
            name=name,
            description=description,
            progress=progress,
            status=status,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            color=color   # ←追加
        )
        db.session.add(pj)
        db.session.commit()
        return redirect(url_for('list_projects'))
    return render_template('project_form.html', project=None)

@app.route('/admin/fix_project_colors')
def fix_project_colors():
    projects = Project.query.all()
    for idx, pj in enumerate(projects):
        if not pj.color:
            pj.color = list(PROJECT_COLORS.values())[idx % len(PROJECT_COLORS)]
    db.session.commit()
    return "Project colors fixed"

# 新規プロジェクト作成
@app.route('/project/create', methods=['POST'])
def create_project():
    name = request.form['name']
    description = request.form.get('description', '')
    p = Project(name=name, description=description)
    db.session.add(p)
    db.session.commit()
    return redirect(url_for('list_projects'))

# 詳細画面ルート
@app.route('/project/<int:project_id>')
def project_detail(project_id):
    p = Project.query.get_or_404(project_id)
    themes = Theme.query.filter_by(project_id=project_id).all()
    progress = calc_project_progress(project_id)
    return render_template('project_detail.html', project=p, themes=themes, progress=progress)



@app.route('/project/edit/<int:project_id>', methods=['GET', 'POST'])
def edit_project(project_id):
    pj = Project.query.get_or_404(project_id)
    if request.method == 'POST':
        pj.name = request.form['name']
        pj.description = request.form['description']
        pj.progress = int(request.form.get('progress', 0))
        pj.status = request.form['status']
        scheduled_start_raw = request.form.get('scheduled_start') or None
        scheduled_end_raw = request.form.get('scheduled_end') or None
        pj.scheduled_start = datetime.strptime(scheduled_start_raw, "%Y-%m-%d").date() if scheduled_start_raw else None
        pj.scheduled_end = datetime.strptime(scheduled_end_raw, "%Y-%m-%d").date() if scheduled_end_raw else None

        pj.color = request.form.get('color') or pj.color
        db.session.commit()
        return redirect(url_for('list_projects'))
    return render_template('project_form.html', project=pj)

@app.route('/project/delete/<int:project_id>', methods=['GET', 'POST'])
def delete_project(project_id):
    pj = Project.query.get_or_404(project_id)
    if request.method == 'POST':
        db.session.delete(pj)
        db.session.commit()
        return redirect(url_for('list_projects'))
    # GETリクエストなら本当に消すか確認ページにしてもよいが、ここでは即削除
    db.session.delete(pj)
    db.session.commit()
    return redirect(url_for('list_projects'))

# 3 テーマ一覧+作成・詳細画面
# 3-1. 一覧ルート
@app.route('/themes')
def list_themes():
    themes = Theme.query.all()
    projects = {pj.id: pj for pj in Project.query.all()}
    return render_template('theme_list.html', themes=themes, projects=projects)

# 3-2. 新規テーマ作成（プロジェクト選択も可）
@app.route('/theme/create', methods=['POST'])
def create_theme():
    name = request.form['name']
    project_id = request.form.get('project_id')
    description = request.form.get('description', '')
    detail = request.form.get('detail', '')
    t = Theme(name=name, project_id=project_id, description=description, detail=detail)
    db.session.add(t)
    db.session.commit()
    return redirect(url_for('list_themes'))

@app.route('/theme/new', methods=['GET', 'POST'])
def new_theme():
    projects = Project.query.all()
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        progress = int(request.form.get('progress', 0))
        status = request.form['status']
        # ここで型変換！「date」型を「datetime.date」へ
        scheduled_start_raw = request.form.get('scheduled_start') or None
        scheduled_end_raw = request.form.get('scheduled_end') or None
        scheduled_start = datetime.strptime(scheduled_start_raw, "%Y-%m-%d").date() if scheduled_start_raw else None
        scheduled_end = datetime.strptime(scheduled_end_raw, "%Y-%m-%d").date() if scheduled_end_raw else None

        project_id = request.form.get('project_id') or None
        th = Theme(
            name=name,
            description=description,
            progress=progress,
            status=status,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            project_id=project_id
        )
        db.session.add(th)
        db.session.commit()
        return redirect(url_for('list_themes'))
    return render_template('theme_form.html', theme=None, projects=projects)

@app.route('/theme/edit/<int:theme_id>', methods=['GET', 'POST'])
def edit_theme(theme_id):
    th = Theme.query.get_or_404(theme_id)
    projects = Project.query.all()
    if request.method == 'POST':
        th.name = request.form['name']
        th.description = request.form['description']
        th.progress = int(request.form.get('progress', 0))
        th.status = request.form['status']
        scheduled_start = request.form.get('scheduled_start') or None
        scheduled_end = request.form.get('scheduled_end') or None
        th.scheduled_start = datetime.fromisoformat(scheduled_start) if scheduled_start else None
        th.scheduled_end = datetime.fromisoformat(scheduled_end) if scheduled_end else None
        th.project_id = request.form.get('project_id') or None
        db.session.commit()
        return redirect(url_for('list_themes'))
    return render_template('theme_form.html', theme=th, projects=projects)

@app.route('/theme/delete/<int:theme_id>')
def delete_theme(theme_id):
    th = Theme.query.get_or_404(theme_id)
    db.session.delete(th)
    db.session.commit()
    return redirect(url_for('list_themes'))

@app.route('/theme/<int:theme_id>')
def theme_detail(theme_id):
    th = Theme.query.get_or_404(theme_id)
    project = th.project if th.project_id else None
    # 紐づくタスク一覧
    tasks = Task.query.filter_by(theme_id=theme_id).order_by(Task.scheduled_start).all()
    # 作業実績ページ用リンク生成（既存ならworklog.id, 無ければNone）
    worklog_map = {t.id: TaskWorkLog.query.filter_by(task_id=t.id).first() for t in tasks}
    return render_template('theme_detail.html', theme=th, project=project, tasks=tasks, worklog_map=worklog_map)

# 4. タスク作成
@app.route('/task/new', methods=['GET', 'POST'])
def create_task():
    projects = Project.query.all()
    project_id = request.args.get('project_id')
    if project_id:
        themes = Theme.query.filter_by(project_id=project_id).all()
    else:
        themes = Theme.query.all()
    # themes = Theme.query.all()
    selected_project_id = request.args.get('project_id')
    selected_theme_id = request.args.get('theme_id')      # テーマID ←ここ！

    if request.method == 'POST':
        title = request.form['title']
        detail = request.form.get('detail', '')

        scheduled_start = request.form.get('scheduled_start') or None
        scheduled_end = request.form.get('scheduled_end') or None
        weight = int(request.form.get('weight', 10))
        status = request.form.get('status', '未着手')
        # is_completed = 'is_completed' in request.form
        project_id = request.form.get('project_id') or None
        theme_id = request.form.get('theme_id') or None
        t = Task(
            title=title,
            detail=detail,
            scheduled_start=datetime.fromisoformat(scheduled_start) if scheduled_start else None,
            scheduled_end=datetime.fromisoformat(scheduled_end) if scheduled_end else None,
            weight=weight,
            status=status,
            # is_completed=is_completed,
            project_id=project_id,
            theme_id=theme_id
        )
        db.session.add(t)
        db.session.commit()
        
        # 進捗自動計算
        if t.theme_id:
            update_theme_progress(t.theme_id)
        if t.project_id:
            update_project_progress(t.project_id)
            return redirect(url_for('calendar_view'))
    # GET時
    return render_template(
        'task_form.html',
        projects=projects,
        themes=themes,
        selected_project_id=selected_project_id,
        selected_theme_id=selected_theme_id,
    )

# 編集用も同様に
@app.route('/task/edit/<int:task_id>', methods=['GET', 'POST'])
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    projects = Project.query.all()
    themes = Theme.query.all()

    if request.method == 'POST':
        task.title = request.form['title']
        task.detail = request.form['detail']
        scheduled_start = request.form.get('scheduled_start') or None
        scheduled_end = request.form.get('scheduled_end') or None
        
        task.scheduled_start = datetime.fromisoformat(scheduled_start) if scheduled_start else None
        task.scheduled_end = datetime.fromisoformat(scheduled_end) if scheduled_end else None
        task.weight = int(request.form.get('weight', 10))
        task.status = request.form['status']
        # task.is_completed = request.form.get('is_completed') or None
        task.project_id = request.form.get('project_id') or None
        task.theme_id = request.form.get('theme_id') or None

        db.session.commit()
        
        # 進捗自動計算
        if task.theme_id:
            update_theme_progress(task.theme_id)
        if task.project_id:
            update_project_progress(task.project_id)
        return redirect(url_for('calendar_view'))

    return render_template(
        'task_form.html',
        task=task,
        projects=projects,
        themes=themes,
        selected_project_id=task.project_id,
        selected_theme_id=task.theme_id,
    )


@app.route('/api/task/<int:task_id>')
def get_task(task_id):
    task = Task.query.get_or_404(task_id)
    worklogs = sorted(task.worklogs, key=lambda w: w.start_at or datetime.min)
    latest_worklog_id = worklogs[-1].id if worklogs else None
    return jsonify({
        "id": task.id,
        "title": task.title,
        "detail": task.detail,
        "scheduled_start": task.scheduled_start.isoformat() if task.scheduled_start else "",
        "scheduled_end": task.scheduled_end.isoformat() if task.scheduled_end else "",
        "weight": task.weight,
        "status": task.status,
        "is_completed": task.is_completed,
        "theme_id": task.theme_id,
        "project_id": task.project_id,
        "latest_worklog_id": latest_worklog_id
    })

def parse_datetime_with_jst(dtstr):
    # JST = timezone(timedelta(hours=9))
    # # タイムゾーン付きならOK
    # dt = datetime.fromisoformat(dtstr)
    # if dt.tzinfo is None:
    #     # タイムゾーン情報がなければJSTを付与
    #     dt = dt.replace(tzinfo=JST)
    # else:
    #     # 別TZならJSTに変換
    #     dt = dt.astimezone(JST)
    # return dt
    if not dtstr:
        return None
    
    print(dtstr, parse_dt(dtstr))
    JST = timezone(timedelta(hours=9))
    dt = datetime.fromisoformat(dtstr)
    if dt.tzinfo is None:
        # タイムゾーン情報がなければJSTを付与
        dt = dt.replace(tzinfo=JST)
    else:
        # 別TZならJSTに変換
        dt = dt.astimezone(JST)
    # return parse_dt(dtstr)
    return dt

@app.route('/task/update/<int:task_id>', methods=['POST'])
def update_task(task_id):
    task = Task.query.get_or_404(task_id)
    data = request.form or request.json  # どちらからでもOK
    # 日付フィールド（必ず送る場合は上書きでOK）
    if data.get('scheduled_start'):
        task.scheduled_start = parse_datetime_with_jst(data['scheduled_start'])
    if data.get('scheduled_end'):
        task.scheduled_end = parse_datetime_with_jst(data['scheduled_end'])

    # プロジェクト・テーマなどのIDは「値があれば更新、なければ維持」
    project_id = data.get('project_id')
    if project_id is not None and str(project_id).strip() != '':
        task.project_id = int(project_id)
    # 何も送ってこなければ現状維持

    theme_id = data.get('theme_id')
    if theme_id is not None and str(theme_id).strip() != '':
        task.theme_id = int(theme_id)

    def task_to_dict(task):
        d = {}
        for c in task.__table__.columns:
            v = getattr(task, c.name)
            if isinstance(v, datetime):
                d[c.name] = v.isoformat()
            else:
                d[c.name] = v
        return d

    before = json.dumps(task_to_dict(task))


    task.project_id = request.form.get('project_id', task.project_id) or None
    task.theme_id = request.form.get('theme_id', task.theme_id) or None
    task.created_at = request.form.get('created_at')

    # 受け取った値で上書き
    task.title = request.form.get('title', task.title)
    task.detail = request.form.get('detail', task.detail)
    
    # ここでISOフォーマットの文字列で送られてくる
    scheduled_start = request.form.get('scheduled_start')
    scheduled_end = request.form.get('scheduled_end')

    if scheduled_start:
        task.scheduled_start = parse_datetime_with_jst(scheduled_start)
    if scheduled_end:
        task.scheduled_end = parse_datetime_with_jst(scheduled_end)
    task.weight = int(request.form.get('weight', task.weight or 10))
    task.status = request.form.get('status', task.status)
    # チェックボックスは値がなければ未チェック
    # task.is_completed = request.form.get('is_completed', task.is_completed)
    # task.is_completed = 'is_completed' in request.form
    # task.is_completed = request.form.get('is_completed', task.is_completed)

    task.worklogs = request.form.get('worklogs', task.worklogs)
    task.parent_task_id = request.form.get('parent_task_id', task.parent_task_id)
    task.subtasks = request.form.get('subtasks', task.subtasks)

    db.session.commit()
    after = json.dumps(task_to_dict(task))

    
    # 進捗自動計算
    if task.theme_id:
        update_theme_progress(task.theme_id)
    if task.project_id:
        update_project_progress(task.project_id)
    return jsonify({"result": "success"})


@app.route('/api/task/update_status/<int:task_id>', methods=['POST'])
def update_task_status(task_id):
    task = Task.query.get_or_404(task_id)
    status = request.form['status']
    task.status = status
    db.session.commit()
    
    # 進捗自動計算
    if task.theme_id:
        update_theme_progress(task.theme_id)
    if task.project_id:
        update_project_progress(task.project_id)
    return jsonify({'result': 'success'})


@app.route('/api/task/delete/<int:task_id>', methods=['POST'])
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    before = json.dumps({c.name: getattr(task, c.name) for c in task.__table__.columns})
    log = UndoRedoLog(
        action_type='delete',
        target_table='Task',
        target_id=task_id,
        data_before=before,
        data_after=None
    )
    db.session.add(log)
    db.session.delete(task)
    db.session.commit()
    
    # 進捗自動計算
    if task.theme_id:
        update_theme_progress(task.theme_id)
    if task.project_id:
        update_project_progress(task.project_id)
    return jsonify({"result": "deleted"})


@app.route('/tasks')
def list_tasks():
    # tasks = Task.query.all()
    tasks = Task.query.order_by(Task.scheduled_start).all()
    return render_template('task_list.html', tasks=tasks)


@app.route('/task/split/<int:task_id>', methods=['POST'])
def split_task(task_id):
    task = Task.query.get_or_404(task_id)
    split_time_str = request.form.get('split_time')
    split_title_a = request.form.get('split_title_a') or f"{task.title}（前半）"
    split_title_b = request.form.get('split_title_b') or f"{task.title}（後半）"
    split_time = datetime.fromisoformat(split_time_str)
    # バリデーション
    if not (task.scheduled_start < split_time < task.scheduled_end):
        return "分割点は開始～終了の間で指定してください", 400
    
    
    # --- 作業時間計算（秒単位） ---
    total = (task.scheduled_end - task.scheduled_start).total_seconds()
    before = (split_time - task.scheduled_start).total_seconds()
    after = (task.scheduled_end - split_time).total_seconds()
    if total == 0:
        weight_a = weight_b = task.weight // 2
    else:
        weight_a = int(round(task.weight * (before / total)))
        weight_b = task.weight - weight_a  # 誤差調整

    # 新タスクA
    task_a = Task(
        title=split_title_a,
        detail=task.detail,
        scheduled_start=task.scheduled_start,
        scheduled_end=split_time,
        # その他フィールドコピー
        project_id=task.project_id,
        theme_id=task.theme_id,
        weight=weight_a,
        status=task.status,
    )
    # 新タスクB
    task_b = Task(
        title=split_title_b,
        detail=task.detail,
        scheduled_start=split_time,
        scheduled_end=task.scheduled_end,
        project_id=task.project_id,
        theme_id=task.theme_id,
        weight=weight_b,
        status=task.status,
    )
    db.session.add(task_a)
    db.session.add(task_b)
    db.session.delete(task)
    db.session.commit()
    return jsonify({'result': 'success'})


@app.route('/tasks/merge', methods=['POST'])
def merge_tasks():
    task_ids_str = request.form.get('task_ids', '')
    task_ids = [tid for tid in task_ids_str.split(',') if tid]
    if len(task_ids) < 2:
        return "タスクを2つ以上選択してください", 400

    # 統合対象タスクのproject_idを集める
    project_ids = set()
    for tid in task_ids:
        t = Task.query.get(tid)
        if t:
            project_ids.add(t.project_id)

    # 制約1: 異なるproject_idが混じっている場合（None以外）、統合不可
    # project_id=None（フリーログ等）のみの場合は統合可
    if len([pid for pid in project_ids if pid is not None]) > 1:
        return "異なるプロジェクトのタスクは統合できません", 400

    # 入力値
    title = request.form.get('title')
    scheduled_start = request.form.get('scheduled_start')
    scheduled_end = request.form.get('scheduled_end')

    # 統合用情報集約
    details = []
    weight_sum = 0
    status = "未着手"
    project_id = None
    theme_id = None

    # 期間（予定）はフォームの値優先、なければ最小開始～最大終了
    start_dt = None
    end_dt = None


    # 1. 統合元のタスク内容を収集
    for tid in task_ids:
        t = Task.query.get(tid)
        if not t:
            continue
        # details.append(t.detail or "")
        details.append(f"[{t.title}]\n{t.detail or ''}")
        weight_sum += t.weight or 0
        if not project_id:
            project_id = t.project_id
        if not theme_id:
            theme_id = t.theme_id
        # 期間自動計算用
        if t.scheduled_start:
            if not start_dt or t.scheduled_start < start_dt:
                start_dt = t.scheduled_start
        if t.scheduled_end:
            if not end_dt or t.scheduled_end > end_dt:
                end_dt = t.scheduled_end

    # scheduled_start, scheduled_endの型変換
    s_start = datetime.fromisoformat(scheduled_start) if scheduled_start else start_dt
    s_end = datetime.fromisoformat(scheduled_end) if scheduled_end else end_dt

    # 2. 新タスク生成
    merge_task = Task(
        title=title or "統合タスク",
        detail="\n---\n".join(details),
        scheduled_start=s_start,
        scheduled_end=s_end,
        weight=weight_sum,
        status=status,
        project_id=project_id,
        theme_id=theme_id,
        is_completed=False
    )
    db.session.add(merge_task)
    db.session.flush()  # ここでmerge_task.idが付与される

    # 3. 元タスクのWorkLog等を新タスクに移動
    for tid in task_ids:
        t = Task.query.get(tid)
        if not t:
            continue
        for wl in getattr(t, "worklogs", []):
            wl.task_id = merge_task.id
        db.session.delete(t)

    db.session.commit()
    return jsonify({'result': 'success', 'redirect': url_for('calendar_view', task_id=merge_task.id)})
 

@app.route('/worklog/new', methods=['GET', 'POST'])
def new_worklog():
    projects = Project.query.all()
    themes = Theme.query.all()
    tasks = Task.query.order_by(Task.scheduled_start).all()

    if request.method == 'GET':
        task_id = request.args.get('task_id')
        # 既に作業実績があればリダイレクト
        if task_id:
            exist = TaskWorkLog.query.filter_by(task_id=task_id).first()
            if exist:
                return redirect(url_for('worklog_page', worklog_id=exist.id))

        log = TaskWorkLog()
        db.session.add(log)
        db.session.commit()

        selected_task = None
        selected_start = None
        # selected_project = None
        # selected_theme = None

        if task_id:
            selected_task = Task.query.get(int(task_id))
            selected_start = selected_task.scheduled_start.strftime('%Y-%m-%dT%H:%M') if selected_task and selected_task.scheduled_start else None
        # log = TaskWorkLog()
            if selected_task:
                log.task_id = selected_task.id
                log.project_id = selected_task.project_id
                log.theme_id = selected_task.theme_id
                # selected_project = Project.query.get(selected_task.project_id) if selected_task.project_id else None
                # selected_theme = Theme.query.get(selected_task.theme_id) if selected_task.theme_id else None
        # db.session.add(log)
        db.session.commit()
        return render_template(
            'worklog_form.html',
            worklog=log,
            tasks=tasks,
            selected_task=selected_task,
            project=projects,
            theme=themes,
            selected_start=selected_start
        )
    else:
        log_id = request.form.get('log_id')
        log = TaskWorkLog.query.get(log_id)
        log.task_id = request.form.get('task_id') or None
        log.project_id = request.form.get('project_id') or None
        log.theme_id = request.form.get('theme_id') or None
        log.start_at = request.form.get('start_at')
        log.end_at = request.form.get('end_at') or None
        log.status = request.form.get('status')
        log.memo = request.form.get('memo', '')
        db.session.commit()
        return redirect(url_for('worklogs'))  # 作業実績一覧などに遷移

from datetime import datetime
@app.route('/api/worklog/set_start/<int:log_id>', methods=['POST'])
def api_set_worklog_start(log_id):
    log = TaskWorkLog.query.get_or_404(log_id)
    now = datetime.now()
    log.start_at = now
    db.session.commit()
    return jsonify({'result': 'ok', 'time': now.strftime('%Y-%m-%d %H:%M:%S')})

@app.route('/api/worklog/set_end/<int:log_id>', methods=['POST'])
def api_set_worklog_end(log_id):
    log = TaskWorkLog.query.get_or_404(log_id)
    now = datetime.now()
    log.end_at = now
    db.session.commit()
    return jsonify({'result': 'ok', 'time': now.strftime('%Y-%m-%d %H:%M:%S')})



# 作業実績編集
@app.route('/worklog/edit/<int:worklog_id>', methods=['GET', 'POST'])
def edit_worklog(worklog_id):
    worklog = TaskWorkLog.query.get_or_404(worklog_id)
    tasks = Task.query.order_by(Task.scheduled_start).all()
    if request.method == 'POST':
        worklog.task_id = request.form.get('task_id')
        worklog.start_at = datetime.strptime(request.form['start_at'], '%Y-%m-%dT%H:%M')
        end_at = request.form.get('end_at')
        worklog.end_at = datetime.strptime(end_at, '%Y-%m-%dT%H:%M') if end_at else None
        worklog.status = request.form.get('status', '実績')
        worklog.memo = request.form.get('memo', '')
        db.session.commit()
        return redirect(url_for('worklogs'))
    return render_template('worklog_form.html', worklog=worklog, tasks=tasks, selected_start=worklog.start_at.strftime('%Y-%m-%dT%H:%M') if worklog.start_at else "")

# 作業実績削除
@app.route('/worklog/delete/<int:worklog_id>', methods=['POST'])
def delete_worklog(worklog_id):
    worklog = TaskWorkLog.query.get_or_404(worklog_id)
    db.session.delete(worklog)
    db.session.commit()
    return redirect(url_for('worklogs'))


@app.route('/worklogs')
def worklogs():
    # 絞り込みや検索は後から追加も可
    logs = TaskWorkLog.query.order_by(TaskWorkLog.start_at.desc()).all()
    # タスク名も一緒に表示したいのでTaskも取得
    task_map = {t.id: t for t in Task.query.all()}
    projects = Project.query.all()
    project_map = {pj.id: pj for pj in projects}
    return render_template(
        'worklog_list.html',
        logs=logs,
        task_map=task_map,
        project_map=project_map

        )

# UI
# ガントチャート用ルート追加
@app.route('/gantt')
def gantt_chart():
    projects = Project.query.order_by(Project.name).all()
    return render_template('gantt.html', projects=projects)

@app.route('/api/gantt')
def gantt_data():
    level = request.args.get('level', 'all')
    project_id = request.args.get('project_id', type=int)
    # プロジェクト・テーマ・タスクをガントチャート向けデータ構造に変換
    tasks = []
    # プロジェクト絞り込み
    if project_id:
        projects = Project.query.filter_by(id=project_id).all()
        themes = Theme.query.filter_by(project_id=project_id).all()
        theme_ids = [th.id for th in themes]
        task_objs = Task.query.filter(
            (Task.project_id == project_id) |
            (Task.theme_id.in_(theme_ids))
        ).all()
    else:
        projects = Project.query.all()
        themes = Theme.query.all()
        task_objs = Task.query.all()
    # プロジェクト
    if level in ('all', 'project'):
        for p in projects:
            tasks.append({
                "id": f"project-{p.id}",
                "name": f"[PJ] {p.name}",
                "start": p.scheduled_start.isoformat() if p.scheduled_start else "",
                "end": p.scheduled_end.isoformat() if p.scheduled_end else "",
                "progress": p.progress or 0,
                "custom_class": "project-bar",
                "color": p.color or "#d3d3d3",
                "parent": "",
            })
    # テーマ
    if level in ('all', 'theme'):
        for t in themes:
            parent_id = f"project-{t.project_id}" if t.project_id else ""
            tasks.append({
                "id": f"theme-{t.id}",
                "name": f"[テーマ] {t.name}",
                "start": t.scheduled_start.isoformat() if t.scheduled_start else "",
                "end": t.scheduled_end.isoformat() if t.scheduled_end else "",
                "progress": t.progress or 0,
                "custom_class": "theme-bar",
                "color": Project.query.get(t.project_id).color if t.project_id else "#d3d3d3",
                "parent": parent_id,
            })
    # タスク
    if level in ('all', 'task'):
        # task_objs = Task.query.all()
        for tk in task_objs:
            parent_id = ''
            if tk.theme_id:
                parent_id = f"theme-{tk.theme_id}"
            elif tk.project_id:
                parent_id = f"project-{tk.project_id}"
            else:
                parent_id = ''
            project = Project.query.get(tk.project_id) if tk.project_id else None
            project_color = project.color if (project and getattr(project, "color", None)) else "#d3d3d3"
            # project_color = Project.query.get(tk.project_id).color if tk.project_id else "#d3d3d3"
            tasks.append({
                "id": f"task-{tk.id}",
                "name": tk.title,
                "start": tk.scheduled_start.isoformat() if tk.scheduled_start else "",
                "end": tk.scheduled_end.isoformat() if tk.scheduled_end else "",
                "progress": 100 if tk.is_completed else 0,
                "custom_class": "task-bar",
                "color": project_color,
                "parent": parent_id,
            })
    return jsonify(tasks)

@app.route('/api/projects')
def api_projects():
    projects = Project.query.order_by(Project.name).all()
    return jsonify([{'id': p.id, 'name': p.name} for p in projects])


@app.route('/undo', methods=['POST'])
def undo():
    last_action = UndoRedoLog.query.filter_by(undone=False).order_by(UndoRedoLog.timestamp.desc()).first()
    if not last_action:
        return jsonify({'result': 'no action'})

    if last_action.action_type == 'split':
        print("SPLIT UNDO: after=", last_action.data_after)
        print("SPLIT UNDO: before=", last_action.data_before)
        # 分割時→分割後2タスクを削除し、元タスクを復元
        after = json.loads(last_action.data_after)
        for t_data in after:
            t = Task.query.get(t_data['id'])
            if t:
                print("Task count after undo:", Task.query.count())
                db.session.delete(t)
        db.session.commit()  # 一度コミットしてID解放
        # 元タスクを復元
        before = json.loads(last_action.data_before)
        t = Task(**before)
        print("Task count after undo:", Task.query.count())
        db.session.add(t)
        db.session.commit()

    elif last_action.action_type == 'merge':
        print("MERGE UNDO: after=", last_action.data_after)
        print("MERGE UNDO: before=", last_action.data_before)
        # 統合時→統合タスクを削除し、元タスク群を復元
        after = json.loads(last_action.data_after)
        m = Task.query.get(after['id'])
        if m:
            print("Task count after undo:", Task.query.count())
            db.session.delete(m)
        db.session.commit()
        # 元タスク群を復元
        for t_data in json.loads(last_action.data_before):
            t = Task(**t_data)
            print("Task count after undo:", Task.query.count())
            db.session.add(t)
        db.session.commit()

    # 既存のdelete/update等も必要ならcase分岐
    last_action.undone = True
    db.session.commit()
    return jsonify({'result': 'success'})


@app.route('/redo', methods=['POST'])
def redo():
    # undone=Trueのうち一番古いもの
    last_undone = UndoRedoLog.query.filter_by(undone=True).order_by(UndoRedoLog.timestamp.asc()).first()
    if not last_undone:
        return jsonify({'result': 'no action'})
    if last_undone.target_table == "Task":
        data = json.loads(last_undone.data_after)
        t = Task.query.get(last_undone.target_id)
        if last_undone.action_type == "delete":
            # 削除をredo = 再度削除
            if t:
                db.session.delete(t)
        elif last_undone.action_type == "update":
            if t:
                for k, v in data.items():
                    setattr(t, k, v)
        elif last_undone.action_type == "create":
            if not t:
                t = Task(**data)
                db.session.add(t)
    last_undone.undone = False
    db.session.commit()
    return jsonify({'result': 'success'})

@app.route('/debug/undolog')
def debug_undolog():
    logs = UndoRedoLog.query.order_by(UndoRedoLog.timestamp.desc()).limit(5).all()
    return jsonify([
        {
            'id': log.id,
            'action_type': log.action_type,
            'data_before': log.data_before,
            'data_after': log.data_after,
            'undone': log.undone,
            'timestamp': str(log.timestamp)
        }
        for log in logs
    ])


# 追加の処理；ToDo作成など
@app.route('/todos')
def todos():
    update_task_completion()  # 完了判定を都度更新
    # 未完了かつ未着手・進行中のタスク
    todo_tasks = Task.query.filter(
        Task.is_completed == False,
        Task.status.in_(['未着手', '進行中'])
    ).order_by(Task.scheduled_start).all()
    return render_template('todo_list.html', tasks=todo_tasks)

# app.py 側
@app.route('/todo')
def todo_list():
    tasks = Task.query.order_by(Task.scheduled_start).all()
    projects = Project.query.all()
    project_map = {pj.id: pj.name for pj in projects}
    return render_template('todo_list.html', tasks=tasks, projects=projects, project_map=project_map)

def update_task_completion():
    tasks = Task.query.all()
    for task in tasks:
        # 1件でも紐づくworklogがあれば完了とみなす
        has_log = TaskWorkLog.query.filter_by(task_id=task.id).count() > 0
        if has_log and not task.is_completed:
            task.is_completed = True
        elif not has_log and task.is_completed:
            task.is_completed = False
    db.session.commit()



@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    worklog_id = request.form.get('worklog_id')
    worklog_dir = os.path.join(UPLOAD_DIR, str(worklog_id))
    os.makedirs(worklog_dir, exist_ok=True)
    save_path = os.path.join(worklog_dir, file.filename)
    file.save(save_path)
    # DB登録もしたい場合はここで WorkLogFile を保存
    new_file = WorkLogFile(worklog_id=worklog_id, filename=file.filename)
    db.session.add(new_file)
    db.session.commit()
    return jsonify({'url': f'/uploads/{worklog_id}/{file.filename}'})

@app.route('/uploads/<int:worklog_id>/<filename>')
def uploaded_file(worklog_id, filename):
    return send_from_directory(os.path.join(UPLOAD_DIR, str(worklog_id)), filename)

@app.route('/worklog/page/<int:worklog_id>', methods=['GET', 'POST'])
def worklog_page(worklog_id):
    log = TaskWorkLog.query.get_or_404(worklog_id)
    # 関連タスクを取得
    tasks = Task.query.order_by(Task.scheduled_start).all()
    selected_task = Task.query.get(log.task_id) if log.task_id else None
    # プロジェクト・テーマはタスクからたどる
    # project = selected_task.project if selected_task and hasattr(selected_task, "project") else None
    # theme = selected_task.theme if selected_task and hasattr(selected_task, "theme") else None
    selected_project = Project.query.get(selected_task.project_id) if selected_task and selected_task.project_id else None
    selected_theme = Theme.query.get(selected_task.theme_id) if selected_task and selected_task.theme_id else None

    # 保存処理（例：メモの保存）
    if request.method == 'POST':
        log.memo = request.form.get('memo', '')
        db.session.commit()
        return redirect(url_for('worklog_page', worklog_id=log.id))

    img_folder = os.path.join("static", "files", f"worklog_{worklog_id}")
    img_glob = []
    if os.path.exists(img_folder):
        img_glob = sorted(glob.glob(os.path.join(img_folder, "*.*")))  # jpg, png等を全部取得
    img_urls = ["/" + f.replace("\\", "/") for f in img_glob]  # Flask用パスに変換

    return render_template(
        'worklog_page.html',
        worklog=log,
        img_urls=img_urls,
        tasks=tasks,
        selected_task=selected_task,
        project=selected_project,
        theme=selected_theme,
    )

@app.route("/upload_image", methods=["POST"])
def upload_image():
    file = request.files['image']
    worklog_id = request.form.get("worklog_id")
    print("upload_image for worklog_id=", worklog_id)  # デバッグ用
    # 保存先パス
    folder = os.path.join("static", "files", f"worklog_{worklog_id}")
    os.makedirs(folder, exist_ok=True)
    # ファイル名衝突対策
    filename = file.filename
    base, ext = os.path.splitext(filename)
    i = 1
    while os.path.exists(os.path.join(folder, filename)):
        filename = f"{base}_{i}{ext}"
        i += 1
    path = os.path.join(folder, filename)
    file.save(path)
    # アクセスURLを返す
    url = f"/static/files/worklog_{worklog_id}/{filename}"
    return jsonify({"url": url})

def calc_theme_progress(theme_id):
    tasks = Task.query.filter_by(theme_id=theme_id).all()
    if not tasks:
        return 0
    total_weight = sum(t.weight or 10 for t in tasks)
    if total_weight == 0:
        total_weight = len(tasks)  # 全てweight未設定のときは均等扱い
    done_weight = 0
    for t in tasks:
        # 完了判定: ステータス"完了" or 紐づく作業実績が存在
        has_worklog = TaskWorkLog.query.filter_by(task_id=t.id).first() is not None
        if t.status == '完了' or has_worklog:
            done_weight += t.weight or 10
    progress = int(round(100 * done_weight / total_weight))
    return progress

def calc_project_progress(project_id):
    themes = Theme.query.filter_by(project_id=project_id).all()
    if not themes:
        return 0
    total = 0
    for th in themes:
        total += calc_theme_progress(th.id)
    progress = int(round(total / len(themes)))
    return progress

def update_theme_progress(theme_id):
    progress = calc_theme_progress(theme_id)
    th = Theme.query.get(theme_id)
    if th:
        th.progress = progress
        db.session.commit()
    return progress

def update_project_progress(project_id):
    progress = calc_project_progress(project_id)
    pj = Project.query.get(project_id)
    if pj:
        pj.progress = progress
        db.session.commit()
    return progress

@app.route('/worklog/pin/<int:worklog_id>', methods=['POST'])
def toggle_pin(worklog_id):
    log = TaskWorkLog.query.get_or_404(worklog_id)
    log.is_pinned = not log.is_pinned
    db.session.commit()
    return redirect(request.referrer or url_for('worklogs'))

if __name__ == '__main__':
    with app.app_context():
        # db.drop_all()
        db.create_all()
    app.run(debug=True)
