import os
import time
from flask import Flask, render_template, request, send_file

from compressor import (
    is_image,
    compress_image,
    compress_video
)

# ---------------------------------------------------
# Folder Setup
# ---------------------------------------------------
UPLOAD_FOLDER = "static/uploads"
DOWNLOAD_FOLDER = "static/downloads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["DOWNLOAD_FOLDER"] = DOWNLOAD_FOLDER


# ---------------------------------------------------
# Auto-clean compressed files older than X minutes
# ---------------------------------------------------
def cleanup_old_files(folder, max_age_minutes=30):
    now = time.time()
    max_age_seconds = max_age_minutes * 60

    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        if os.path.isfile(path):
            if now - os.path.getmtime(path) > max_age_seconds:
                os.remove(path)


# ---------------------------------------------------
# Main Route
# ---------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    cleanup_old_files(DOWNLOAD_FOLDER, max_age_minutes=30)

    if request.method == "POST":
        file = request.files.get("file")

        if not file:
            return "No file was uploaded."

        # Save uploaded file
        save_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(save_path)

        # Get user selection
        quality = request.form.get("quality")
        codec = request.form.get("codec")
        resolution = request.form.get("resolution")

        # Process file
        if is_image(save_path):
            output_path = compress_image(save_path)
        else:
            output_path = compress_video(
                save_path,
                quality=quality,
                codec=codec,
                resolution=resolution
            )

        # Move to downloads folder
        final_filename = os.path.basename(output_path)
        final_path = os.path.join(DOWNLOAD_FOLDER, final_filename)

        if os.path.exists(final_path):
            os.remove(final_path)  # Prevent overwrite conflict

        os.replace(output_path, final_path)

        return send_file(final_path, as_attachment=True)

    return render_template("index.html")


# ---------------------------------------------------
# Run App
# ---------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
