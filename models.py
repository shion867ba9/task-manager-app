# models.py

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

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

