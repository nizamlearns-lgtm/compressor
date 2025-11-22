import os
import time
import uuid
import signal
from flask import Flask, render_template, request, send_file, jsonify, url_for

from compressor import (
    is_image,
    compress_image,
    compress_video,
    get_duration,
    start_video_compression_async,
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

# Jobs registry: job_id -> {proc, in_path, out_path, progress_file, duration, status, started}
JOBS = {}


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
@app.route("/", methods=["GET"])
def index():
    cleanup_old_files(DOWNLOAD_FOLDER, max_age_minutes=30)
    return render_template("index.html")


@app.route('/start', methods=['POST'])
def start_job():
    """Start a compression job. Returns JSON with a `job_id`. Client should poll `/progress/<job_id>`.
    """
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'no file uploaded'}), 400

    # Save uploaded file with a unique prefix to avoid collisions
    original_name = file.filename
    job_id = uuid.uuid4().hex
    in_name = f"{job_id}_in_{original_name}"
    in_path = os.path.join(UPLOAD_FOLDER, in_name)
    file.save(in_path)

    quality = request.form.get('quality')
    codec = request.form.get('codec')
    resolution = request.form.get('resolution')

    # Image: process synchronously and return a done job
    if is_image(in_path):
        try:
            out_path = compress_image(in_path)
            final_filename = os.path.basename(out_path)
            final_path = os.path.join(DOWNLOAD_FOLDER, final_filename)
            if os.path.exists(final_path):
                os.remove(final_path)
            os.replace(out_path, final_path)
            JOBS[job_id] = {'status': 'done', 'out_path': final_path, 'original': original_name}
            return jsonify({'job_id': job_id, 'status': 'done', 'download_url': url_for('download_job', job_id=job_id)})
        except Exception as e:
            return jsonify({'job_id': job_id, 'status': 'error', 'error': str(e)}), 500

    # Video: start async ffmpeg with progress file
    out_name = f"{job_id}_out_{original_name}"
    out_path = os.path.join(DOWNLOAD_FOLDER, out_name)
    progress_file = os.path.join(UPLOAD_FOLDER, f"{job_id}.progress")

    duration = get_duration(in_path)

    try:
        proc = start_video_compression_async(in_path, out_path, quality=quality or 'balanced', codec=codec or 'h265', resolution=resolution or 'original', progress_file=progress_file)
    except Exception as e:
        return jsonify({'job_id': job_id, 'status': 'error', 'error': str(e)}), 500

    JOBS[job_id] = {
        'proc': proc,
        'in_path': in_path,
        'out_path': out_path,
        'progress_file': progress_file,
        'duration': duration,
        'status': 'running',
        'original': original_name,
        'started': time.time()
    }

    return jsonify({'job_id': job_id, 'status': 'running'})


@app.route('/progress/<job_id>', methods=['GET'])
def progress(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({'error': 'job not found'}), 404

    status = job.get('status')
    proc = job.get('proc')
    out_path = job.get('out_path')
    progress_file = job.get('progress_file')
    duration = job.get('duration')

    progress_info = {'status': status}

    # Read progress file if present
    out_time = 0.0
    try:
        if progress_file and os.path.exists(progress_file):
            # ffmpeg -progress writes key=value lines; read last snapshot
            with open(progress_file, 'r') as f:
                text = f.read()
            # parse lines
            data = {}
            for line in text.strip().splitlines():
                if '=' in line:
                    k, v = line.split('=', 1)
                    data[k.strip()] = v.strip()
            # out_time_ms available in many ffmpeg builds
            if 'out_time_ms' in data:
                out_time = float(data.get('out_time_ms', '0')) / 1000000.0
            elif 'out_time' in data:
                # out_time like HH:MM:SS.micro
                t = data.get('out_time')
                parts = t.split(':')
                if len(parts) == 3:
                    hh, mm, ss = parts
                    out_time = float(hh) * 3600.0 + float(mm) * 60.0 + float(ss)
            if data.get('progress') == 'end':
                # job finished
                job['status'] = 'done'
                status = 'done'
    except Exception:
        pass

    # If process finished according to OS but job status not set, set it
    if proc and proc.poll() is not None and job.get('status') == 'running':
        job['status'] = 'done'
        status = 'done'

    percent = None
    time_left = None
    if duration and duration > 0:
        percent = min(100.0, (out_time / duration) * 100.0)
        time_left = max(0.0, duration - out_time)

    progress_info.update({'percent': percent, 'time_left': time_left})

    if status == 'done':
        # Ensure output exists
        if os.path.exists(out_path):
            progress_info['download_url'] = url_for('download_job', job_id=job_id)
        else:
            progress_info['error'] = 'output not found'

    return jsonify(progress_info)


@app.route('/download/<job_id>', methods=['GET'])
def download_job(job_id):
    job = JOBS.get(job_id)
    if not job:
        return 'not found', 404
    out_path = job.get('out_path')
    if not out_path or not os.path.exists(out_path):
        return 'not ready', 404
    return send_file(out_path, as_attachment=True)


@app.route('/cancel', methods=['POST'])
def cancel():
    """Best-effort cancel/cleanup endpoint.
    Client may POST JSON {"filename": "original_name.ext"} to request cleanup.
    This cannot forcibly stop a synchronous compression already running in another request,
    but will remove uploaded/download files with that name where possible.
    """
    data = request.get_json(silent=True) or {}
    job_id = data.get('job_id')
    filename = data.get('filename')
    removed = []

    # If job_id provided, try to stop process and remove job files
    if job_id:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({'ok': False, 'error': 'job not found'}), 404
        proc = job.get('proc')
        in_path = job.get('in_path')
        out_path = job.get('out_path')
        progress_file = job.get('progress_file')
        try:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        except Exception:
            pass

        for p in (in_path, out_path, progress_file):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
                    removed.append(p)
            except Exception:
                pass

        # mark job removed
        JOBS.pop(job_id, None)

        return jsonify({'ok': True, 'removed': removed})

    # fallback: accept filename cleanup (legacy)
    if filename:
        for folder in (UPLOAD_FOLDER, DOWNLOAD_FOLDER):
            path = os.path.join(folder, filename)
            try:
                if os.path.exists(path):
                    os.remove(path)
                    removed.append(path)
            except Exception:
                pass
        return jsonify({'ok': True, 'removed': removed})

    return jsonify({'ok': False, 'error': 'missing job_id or filename'}), 400


# ---------------------------------------------------
# Run App
# ---------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
