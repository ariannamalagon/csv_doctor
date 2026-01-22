from file_utils import standardize_column_names, standardize_data_values, clean_dates, clean_amounts, remove_duplicates
import pandas as pd
import os1

DATA_DIR = "csv_doctor/data_storage/"

def process_file(file_input):
    """Process a single CSV file through all cleaning functions"""
    try:
        # Check if it's a full path or just a filename
        if os.path.isabs(file_input) or os.path.exists(file_input):
            input_path = file_input
            directory = os.path.dirname(file_input)
            base_name = os.path.basename(file_input).replace('.csv', '')
        else:
            # Assume it's in data_storage
            input_path = os.path.join(DATA_DIR, file_input)
            directory = DATA_DIR
            base_name = file_input.replace('.csv', '')
        
        # Generate output filename and path
        output_filename = f"{base_name}_cleaned.csv"
        output_path = os.path.join(directory, output_filename)
        
        # Read and process
        try:
            raw_data = pd.read_csv(input_path)
        except FileNotFoundError:
            print(f"Error: File not found at {input_path}")
            return None
        except pd.errors.EmptyDataError:
            print(f"Error: CSV file is empty: {input_path}")
            return None
        except pd.errors.ParserError as e:
            print(f"Error: Could not parse CSV file: {e}")
            return None

        # Validate required columns before cleaning
        required_cols = {"date", "amount", "category", "description"}
        missing = required_cols - set(raw_data.columns)
        if missing:
            print(f"Error: Missing required columns: {', '.join(sorted(missing))}")
            return None
        
        # Apply cleaning functions
        try:
            raw_data = standardize_column_names(raw_data)
            raw_data = standardize_data_values(raw_data)
            raw_data = clean_dates(raw_data)
            raw_data = remove_duplicates(raw_data)
            raw_data = clean_amounts(raw_data)
        except KeyError as e:
            print(f"Error: Missing expected column: {e}")
            return None
        except Exception as e:
            print(f"Error during data cleaning: {e}")
            return None
        
        # Save
        try:
            raw_data.to_csv(output_path, index=False)
        except PermissionError:
            print(f"Error: Permission denied writing to {output_path}")
            return None
        except Exception as e:
            print(f"Error saving file: {e}")
            return None
        
        return output_filename
    
    except Exception as e:
        print(f"Unexpected error processing file: {e}")
        return None

def main():
    print("Welcome to CSV Doctor!")
    print("(Enter filename or full path)")
    files_to_process = []
    
    while True:
        file_input = input("Enter CSV file to clean: ").strip()
        
        # Validate input is not empty
        if not file_input:
            print("Error: Please enter a filename or path.")
            continue
        
        # Determine if it's a path or filename
        if os.path.isabs(file_input) or os.path.exists(file_input):
            file_path = file_input
        else:
            file_path = os.path.join(DATA_DIR, file_input)
        
        # Check if file exists
        if not os.path.exists(file_path):
            print(f"Error: File not found. Please check the path and try again.")
            continue
        
        # Validate it's a CSV file
        if not file_path.lower().endswith('.csv'):
            print("Error: Please provide a CSV file (.csv extension).")
            continue
        
        files_to_process.append(file_input)
        
        # Ask if they want to add more
        add_more = input("Add another file? (y/n): \n\n").strip().lower()
        if add_more != 'y':
            break
    
    # Process all files and track outcomes
    successes = 0
    failures = 0

    for file_input in files_to_process:
        display_name = os.path.basename(file_input)
        print(f"Processing {display_name}...")
        output_filename = process_file(file_input)
        if output_filename:
            print(f"✓ Cleaned: {output_filename}")
            successes += 1
        else:
            print(f"✗ Failed to clean: {display_name}")
            failures += 1
    
    print(f"\nAll done! {len(files_to_process)} file(s) processed. Successes: {successes}, Failures: {failures}.")

if __name__ == "__main__":
    main()
