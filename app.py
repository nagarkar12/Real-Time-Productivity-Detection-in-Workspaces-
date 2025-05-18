from flask import Flask, jsonify
from flask_cors import CORS
from config import Config
from models import db, Person
import csv
from datetime import datetime  # <-- Added for time parsing

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        db.create_all()  # Create tables if they don't exist

    return app

app = create_app()

# Enable CORS for all routes (allow all origins - for development)
CORS(app)

def load_data_from_csv(filename):
    """
    Loads data from a CSV file, calculates duration from time difference, and stores it in the database.
    """
    try:
        with app.app_context():
            with open(filename, 'r') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    try:
                        person_id = int(row['Person ID'])
                        start_time_str = row['Start Time']
                        end_time_str = row['End Time']

                        # Parse start and end times
                        fmt = "%Y-%m-%d %H:%M:%S"  # Adjust format to match your CSV
                        start_time = datetime.strptime(start_time_str, fmt)
                        end_time = datetime.strptime(end_time_str, fmt)

                        # Calculate duration in seconds
                        duration = int((end_time - start_time).total_seconds())

                        work_list = [start_time_str, end_time_str]

                        # Check if person_id already exists
                        existing_person = Person.query.filter_by(person_id=person_id).first()
                        if existing_person:
                            existing_person.duration = duration
                            existing_person.work_list.extend(work_list)
                            db.session.commit()
                            print(f"Updated data for Person ID: {person_id}")
                        else:
                            new_person = Person(person_id=person_id, duration=duration, work_list=work_list)
                            db.session.add(new_person)
                            db.session.commit()
                            print(f"Added data for Person ID: {person_id}")
                    except ValueError:
                        print(f"Skipping row due to invalid data: {row}")
                    except KeyError as e:
                        print(f"Skipping row due to missing key {e}: {row}")

            print("Data loading complete.")

    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

@app.route('/persons', methods=['GET'])
def get_persons():
    try:
        with app.app_context():
            persons = Person.query.all()
            results = [{
                'person_id': person.person_id,
                'duration': person.duration,
                'work_list': person.work_list
            } for person in persons]
            return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    load_data_from_csv('/home/midstan/Desktop/BugSmashers_F&B/Bugsmashers/clean_data.csv')
    app.run(debug=True)
