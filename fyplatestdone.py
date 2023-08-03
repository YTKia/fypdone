import easyocr
import cv2
import numpy as np
import datetime
import sqlite3
import streamlit as st
import re
import pandas as pd
import hashlib
import base64

languages = ['en']

reader = easyocr.Reader(languages, gpu=False) 

conn = sqlite3.connect('stationnement_database.db')
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users
             (username TEXT PRIMARY KEY, password TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS vehicles
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
             plate_number TEXT,
             entry_time DATETIME,
             exit_time DATETIME)''')

def create_user(username, password):
    hashed_password = make_hashes(password)
    c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
              (username, hashed_password))
    conn.commit()

def user_exists(username):
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    return c.fetchone() is not None

def validate_user(username, password):
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    user = c.fetchone()
    if user:
        hashed_password = user[1]
        return check_hashes(password, hashed_password)
    return False

def logout_user():
    st.session_state.login = False

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

st.set_page_config(page_title="Stationnement", layout="wide")

if 'login' not in st.session_state:
    st.session_state.login = False

def login_interface():
    global username
    st.header("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    login_clicked = st.button("Login")
    if login_clicked:
        if validate_user(username, password):
            session_state.login = True
        else:
            st.warning("Invalid username or password!")

def signup_interface():
    st.header("Sign Up")
    new_username = st.text_input("New Username")
    new_password = st.text_input("New Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")
    if new_password != confirm_password:
        st.error("Passwords do not match!")
    elif not is_strong_password(new_password):
        st.warning("Password must be at least 8 characters long and contain a combination of uppercase letters, lowercase letters, numbers, and symbols.")
    elif st.button("Sign Up"):
        if not user_exists(new_username):
            create_user(new_username, new_password)
            st.success("Account created successfully. Please log in.")
        else:
            st.error("An account with that username already exists.")

def is_strong_password(password):
    
    if len(password) < 8:
        return False
    
    if not re.search(r'[A-Z]', password):
        return False
  
    if not re.search(r'[a-z]', password):
        return False

    if not re.search(r'\d', password):
        return False

    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    return True

def display_entry_form():
    st.header("Vehicle Entry")
    uploaded_files = st.file_uploader("Upload Images", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    if uploaded_files:
        for uploaded_file in uploaded_files:
            image = np.array(bytearray(uploaded_file.read()), dtype=np.uint8)
            plate_number = process_image(image)
            if plate_number:
                entry_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                insert_vehicle_record(plate_number, entry_time)
                st.success(f"Vehicle with plate number {plate_number} recorded at {entry_time}")
            else:
                st.warning("No license plate detected in one or more uploaded images.")

def process_image(image):
    img = cv2.imdecode(image, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thresh = cv2.bitwise_not(thresh)
    kernel = np.ones((3, 3), np.uint8)
    masked = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(masked, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_contour_area = 500
    largest_area = 0
    largest_contour = None

    for contour in contours:
        area = cv2.contourArea(contour)
        if area > min_contour_area and area > largest_area:
            largest_area = area
            largest_contour = contour

    if largest_contour is not None:
        x, y, w, h = cv2.boundingRect(largest_contour)
        plate_img = gray[y:y + h, x:x + w]

        result = reader.readtext(plate_img)

        alphanumeric_text = ''
        for detection in result:
            text = detection[1]
            alphanumeric_text += ''.join(filter(str.isalnum, text)) + ' '

        return alphanumeric_text.strip()
    else:
        return None

def display_exit_form():
    st.header("Vehicle Exit")
    uploaded_files = st.file_uploader("Upload Images", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    if uploaded_files:
        for uploaded_file in uploaded_files:
            image = np.array(bytearray(uploaded_file.read()), dtype=np.uint8)
            plate_number = process_image(image)
            if plate_number:
                exit_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                update_vehicle_record_exit_time(plate_number, exit_time)
                st.success(f"Vehicle with plate number {plate_number} exited at {exit_time}")
                record = get_vehicle_record_by_plate(plate_number)
                if record:
                    entry_time = datetime.datetime.strptime(record[2], "%Y-%m-%d %H:%M:%S")
                    duration = calculate_duration(entry_time, datetime.datetime.strptime(exit_time, "%Y-%m-%d %H:%M:%S"))
                    st.info(f"Duration of Stay: {duration}")
            else:
                st.warning("No license plate detected in one or more uploaded images.")

def get_vehicle_record_by_plate(plate_number):
    c.execute("SELECT * FROM vehicles WHERE plate_number = ? ORDER BY entry_time DESC",
              (plate_number,))
    return c.fetchone()

def update_vehicle_record_exit_time(plate_number, exit_time):
    c.execute("UPDATE vehicles SET exit_time = ? WHERE plate_number = ? AND exit_time IS NULL",
              (exit_time, plate_number))
    conn.commit()

def get_latest_id():
    c.execute("SELECT MAX(id) FROM vehicles")
    result = c.fetchone()
    return result[0] if result[0] else 0

def insert_vehicle_record(plate_number, entry_time):
    latest_id = get_latest_id()
    new_id = latest_id + 1

    c.execute("INSERT INTO vehicles (id, plate_number, entry_time) VALUES (?, ?, ?)",
              (new_id, plate_number, entry_time))
    conn.commit()

    # Update the IDs of remaining records in the database
    c.execute("SELECT id FROM vehicles WHERE id > ? ORDER BY id ASC", (new_id,))
    records_to_update = c.fetchall()
    for record in records_to_update:
        c.execute("UPDATE vehicles SET id=? WHERE id=?", (new_id, record[0]))
        new_id += 1
    conn.commit()

def calculate_duration(entry_time, exit_time):
    duration = exit_time - entry_time
    days, seconds = duration.days, duration.seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    duration_string = f"{days} days, {hours} hours, {minutes} minutes"
    return duration_string

def display_records_table():
    st.header("Vehicle Records")
    # Sort records in ascending order by ID
    c.execute("SELECT * FROM vehicles ORDER BY id ASC")  
    records = c.fetchall()

    # Add search widgets
    search_plate = st.text_input("Search by Plate Number")
    search_time = st.text_input("Search by Entry/Exit Time (YYYY-MM-DD HH:MM:SS)")

    if records:
        # Filter records based on search criteria
        filtered_records = []
        for record in records:
            entry_time = datetime.datetime.strptime(record[2], "%Y-%m-%d %H:%M:%S")
            exit_time = datetime.datetime.strptime(record[3], "%Y-%m-%d %H:%M:%S") if record[3] else None

            # Filter by plate number
            if search_plate and search_plate.lower() not in record[1].lower():
                continue

            # Filter by entry/exit time
            if search_time:
                search_time_dt = datetime.datetime.strptime(search_time, "%Y-%m-%d %H:%M:%S")
                if search_time_dt > entry_time or (exit_time and search_time_dt > exit_time):
                    continue

            duration = calculate_duration(entry_time, exit_time) if exit_time else "N/A"
            filtered_records.append({"ID": record[0], "Plate Number": record[1], "Entry Time": entry_time, "Exit Time": exit_time, "Duration": duration})

        if filtered_records:
            st.write("Total Records:", len(filtered_records))
            st.table(pd.DataFrame(filtered_records))
        else:
            st.warning("No matching records found.")
    else:
        st.warning("No records found.")

def edit_record():
    st.header("Edit/Modify Records")

    with st.form(key='edit_record_form'):
        record_id = st.text_input("Enter Record ID to Edit")

        # Create a button to search for the record
        search_button = st.form_submit_button("Search Record")

        # Check if the user has entered a valid record ID and if it exists in the database
        record_to_edit = None
        try:
            if record_id and not record_id.isdigit():
                raise ValueError("Invalid record ID. Please enter a valid numeric ID.")
            elif record_id:
                record_id = int(record_id)
                c.execute("SELECT * FROM vehicles WHERE id=?", (record_id,))
                record_to_edit = c.fetchone()

                if not record_to_edit:
                    st.warning("No record found with the given ID.")
        except ValueError as e:
            st.warning(str(e))
            return

        if record_to_edit:
            # Display the existing data for the selected record
            st.write("Current Record:")
            st.write("ID:", record_to_edit[0])
            st.write("Plate Number:", record_to_edit[1])
            st.write("Entry Time:", record_to_edit[2])
            st.write("Exit Time:", record_to_edit[3] if record_to_edit[3] else "N/A")

            # Allow the user to modify the record using text inputs
            plate_number = st.text_input("Enter New Plate Number", record_to_edit[1])
            entry_time = st.text_input("Enter New Entry Time (YYYY-MM-DD HH:MM:SS)", record_to_edit[2])
            exit_time = st.text_input("Enter New Exit Time (YYYY-MM-DD HH:MM:SS)", record_to_edit[3] if record_to_edit[3] else "")

            # Create a button to update the record
            if st.form_submit_button("Update Record"):
                try:
                    # Update the record with the new data
                    c.execute("UPDATE vehicles SET plate_number=?, entry_time=?, exit_time=? WHERE id=?",
                              (plate_number, entry_time, exit_time, record_id))
                    conn.commit()
                    st.success("Record updated successfully.")
                except Exception as e:
                    st.error(f"An error occurred while updating the record: {str(e)}")
        else:
            if search_button:
                st.warning("Please enter a valid record ID to edit.")

def delete_record():
    st.header("Delete Records")

    # Allow the user to input the record ID to delete
    record_id = st.number_input("Enter Record ID")

    if st.button("Show Record"):
        # Fetch the record with the given record ID
        c.execute("SELECT * FROM vehicles WHERE id=?", (record_id,))
        record = c.fetchone()

        # Check if the record with the given ID exists
        if not record:
            st.warning("No record found with the given ID.")
        else:
            # Calculate the duration of stay if exit time is available
            duration = None
            if record[3]:
                entry_time = datetime.datetime.strptime(record[2], "%Y-%m-%d %H:%M:%S")
                exit_time = datetime.datetime.strptime(record[3], "%Y-%m-%d %H:%M:%S")
                duration = calculate_duration(entry_time, exit_time)

            # Display the existing data for the selected record
            st.write("Record to Delete:")
            st.write("ID:", record[0])
            st.write("Plate Number:", record[1])
            st.write("Entry Time:", record[2])
            st.write("Exit Time:", record[3] if record[3] else "N/A")
            st.write("Duration:", duration)

    # Create a confirmation button to delete the record
    if st.button("Confirm Deletion"):
        # Check if the user has entered a valid record ID
        if record_id is not None:
            try:
                # Delete the record with the given record ID
                c.execute("DELETE FROM vehicles WHERE id=?", (int(record_id),))
                conn.commit()

                # Update the record IDs
                c.execute("SELECT id FROM vehicles ORDER BY id ASC")
                updated_ids = c.fetchall()
                for i, record in enumerate(updated_ids, start=1):
                    new_id = i
                    old_id = record[0]
                    if new_id != old_id:
                        c.execute("UPDATE vehicles SET id=? WHERE id=?", (new_id, old_id))
                        conn.commit()

                st.success("Record deleted successfully.")

            except Exception as e:
                st.error(f"An error occurred while deleting the record: {str(e)}")
        else:
            st.warning("Please enter a valid record ID to delete.")


def generate_report():
    st.header("Generate Report")
    report_type = st.selectbox("Select Report Type", ("None","Daily Report", "Monthly Report"))
    if report_type == "None":
        pass
    elif report_type == "Daily Report":
        generate_daily_report()
    elif report_type == "Monthly Report":
        generate_monthly_report()

def generate_daily_report():
    st.subheader("Daily Report Generator")
    selected_date = st.date_input("Select Date", datetime.datetime.today())
    st.info(f"Generating Daily Report for {selected_date}")

    # Fetch data from the SQLite database based on selected_date and generate the report.
    c.execute("SELECT * FROM vehicles WHERE entry_time BETWEEN ? AND ? ORDER BY entry_time ASC",
              (selected_date.strftime("%Y-%m-%d 00:00:00"), selected_date.strftime("%Y-%m-%d 23:59:59")))
    records = c.fetchall()

    if records:
        st.write("Total Vehicles Entered:", len(records))
        table_data = []
        for record in records:
            entry_time = datetime.datetime.strptime(record[2], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
            exit_time = datetime.datetime.strptime(record[3], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S") if record[3] else "N/A"
            duration = calculate_duration(datetime.datetime.strptime(record[2], "%Y-%m-%d %H:%M:%S"),
                                          datetime.datetime.strptime(record[3], "%Y-%m-%d %H:%M:%S") if record[3] else datetime.datetime.now())
            table_data.append([record[0], record[1], entry_time, exit_time, duration])

        # Create a DataFrame from the table_data list
        df = pd.DataFrame(table_data, columns=["ID", "Plate Number", "Entry Time", "Exit Time", "Duration"])

        # Save the DataFrame to a CSV file
        csv_file = df.to_csv(index=False)
        b64 = base64.b64encode(csv_file.encode()).decode()
        filename = f"Daily_Report_{selected_date.strftime('%Y-%m-%d')}.csv"
        href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">Download {filename}</a>'
        st.markdown(href, unsafe_allow_html=True)

        # Display the report in a table
        # st.table(df)

    else:
        st.warning("No records found for the selected date.")

def generate_monthly_report():
    st.subheader("Monthly Report Generator")
    selected_month = st.date_input("Select Month", datetime.datetime.today().replace(day=1))
    st.info(f"Generating Monthly Report for {selected_month}")

    # Fetch data from the SQLite database based on selected_month and generate the report.
    first_day = selected_month.replace(day=1)
    last_day = (first_day + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
    c.execute("SELECT * FROM vehicles WHERE entry_time BETWEEN ? AND ? ORDER BY entry_time ASC",
              (first_day.strftime("%Y-%m-%d 00:00:00"), last_day.strftime("%Y-%m-%d 23:59:59")))
    records = c.fetchall()

    if records:
        st.write("Total Vehicles Entered:", len(records))
        table_data = []
        for record in records:
            entry_time = datetime.datetime.strptime(record[2], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
            exit_time = datetime.datetime.strptime(record[3], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S") if record[3] else "N/A"
            duration = calculate_duration(datetime.datetime.strptime(record[2], "%Y-%m-%d %H:%M:%S"),
                                          datetime.datetime.strptime(record[3], "%Y-%m-%d %H:%M:%S") if record[3] else datetime.datetime.now())
            table_data.append([record[0], record[1], entry_time, exit_time, duration])

        # Create a DataFrame from the table_data list
        df = pd.DataFrame(table_data, columns=["ID", "Plate Number", "Entry Time", "Exit Time", "Duration"])

        # Save the DataFrame to a CSV file
        csv_file = df.to_csv(index=False)
        b64 = base64.b64encode(csv_file.encode()).decode()
        filename = f"Monthly_Report_{selected_month.strftime('%Y-%m')}.csv"
        href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">Download {filename}</a>'
        st.markdown(href, unsafe_allow_html=True)

        # Display the report in a table
        # st.table(df)

    else:
        st.warning("No records found for the selected month.")

# Authentication interface
def authentication():
    global session_state
    session_state = st.session_state
    if session_state.login:
        st.sidebar.title("Welcome!")
        logout_clicked = st.sidebar.button("Logout")
        if logout_clicked:
            logout_user()
    else:
        page = st.radio("Choose an option", ("Login", "Sign Up"))
        if page == "Login":
            login_interface()
        elif page == "Sign Up":
            signup_interface()

# Main function: Streamlit user interface
if __name__ == "__main__":
    st.title("Stationnement")
    authentication()
    
    if session_state.login:
        st.sidebar.subheader("Options")
        option = st.sidebar.selectbox("Select an option",
                                      ("Record Entry", "Record Exit", "View Records", "Edit/Modify Records", "Delete Records", "Generate Report"))
        if option == "Record Entry":
            display_entry_form()
        elif option == "Record Exit":
            display_exit_form()
        elif option == "View Records":
            display_records_table()
        elif option == "Edit/Modify Records":
            edit_record()
        elif option == "Delete Records":
            delete_record()
        elif option == "Generate Report":
            generate_report()


st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    Developed By
    
    Supervisor:  
    Encik Nor Azmi bin Kadarisman
    
    Group Members:  
    Kia Yi Tong (01DDT21F1020)  
    Intan Maisarah Binti Mohd Rejal
    (01DDT21F1013)  
    Farin Batrisyia Binti Saipul Nizam
    (01DDT21F1007)
    """
)
