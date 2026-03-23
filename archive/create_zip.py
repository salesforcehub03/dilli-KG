import os
import zipfile

def create_project_zip(zip_filename="dili_project_deploy.zip"):
    # Files and extensions to exclude
    exclude_files = {
        '.env', 'create_zip.py', 'cloudflared.exe', 'ngrok.exe', 'ngrok.log', 'cloudflare.log', 
        'extract_output.txt', 'extract_output_post.txt', 'preclinical_output.txt',
        'check_preclinical.py', 'extract_info.py', 'remove_drug_adverse_events.py', 
        'update_graph.py', 'verify_preclinical.py'
    }
    exclude_extensions = {'.exe', '.log', '.zip', '.pyc'}
    exclude_dirs = {'__pycache__', '.git', '.vscode', '.idea'}

    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk('.'):
            # Exclude directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                if file in exclude_files:
                    continue
                if any(file.endswith(ext) for ext in exclude_extensions):
                    continue
                    
                file_path = os.path.join(root, file)
                # Keep relative path inside the zip file
                arcname = os.path.relpath(file_path, start='.')
                zipf.write(file_path, arcname)
                print(f"Added {arcname}")

    print(f"\nSuccessfully created {zip_filename}")

if __name__ == "__main__":
    create_project_zip()
