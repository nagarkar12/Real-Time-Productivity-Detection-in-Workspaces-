from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Person(db.Model):
    __tablename__ = 'person'
    person_id = db.Column(db.Integer, primary_key=True)
    duration = db.Column(db.Integer)
    work_list = db.Column(db.ARRAY(db.String)) # Store start and end times as a list of strings

    def __init__(self, person_id, duration, work_list):
        self.person_id = person_id
        self.duration = duration
        self.work_list = work_list

    def __repr__(self):
        return f'<Person(person_id={self.person_id}, duration={self.duration}, work_list={self.work_list})>'