from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename

from config import Config
from models.course_manager import CourseManager
from models.resume_processor import ResumeProcessor
from models.recommendation_engine import RecommendationEngine

# ----------------------------------
# App setup
# ----------------------------------
app = Flask(__name__)
app.config.from_object(Config)

# ✅ Enable CORS for React / MERN
CORS(app, supports_credentials=True)

# ----------------------------------
# Prepare upload folder
# ----------------------------------
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ----------------------------------
# Initialize components (load once)
# ----------------------------------
print("Loading course data...")
course_manager = CourseManager()

print("Initializing resume processor...")
resume_processor = ResumeProcessor()

print("Initializing recommendation engine...")
recommendation_engine = RecommendationEngine(course_manager)

print("MOOC Resume Feature API ready!")

# ----------------------------------
# Helpers
# ----------------------------------
def allowed_file(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in app.config["ALLOWED_EXTENSIONS"]
    )

def extract_course_url(rec: dict) -> str:
    """
    🔥 NORMALIZE ALL POSSIBLE LINK FORMATS INTO ONE STRING
    """

    # 1️⃣ Direct fields
    for key in ["course_url", "course_link", "url", "course_href"]:
        val = rec.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val

    # 2️⃣ sources field (list)
    sources = rec.get("sources")

    if isinstance(sources, list) and len(sources) > 0:
        first = sources[0]

        # sources = ["https://..."]
        if isinstance(first, str) and first.startswith("http"):
            return first

        # sources = [{"url": "..."}]
        if isinstance(first, dict):
            for k in ["url", "course_url", "course_link", "href"]:
                v = first.get(k)
                if isinstance(v, str) and v.startswith("http"):
                    return v

    return ""

# ----------------------------------
# Root health check
# ----------------------------------
@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "status": "ok",
        "service": "mooc-resume-feature-api"
    }), 200

# ----------------------------------
# Upload Resume (API)
# ----------------------------------
@app.route("/upload", methods=["POST", "OPTIONS"])
def upload_resume():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200

    if "resume" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["resume"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({
            "error": "Invalid file type. Upload PDF or DOCX only."
        }), 400

    filepath = None

    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        # Resume analysis
        analysis = resume_processor.process_resume(filepath)
        if not analysis:
            raise ValueError("Resume processing failed")

        # Recommendations
        recommendations = recommendation_engine.get_recommendations(analysis)

        return jsonify({
            "success": True,
            "analysis": {
                "skills": analysis.get("skills", [])[:20],
                "skill_count": analysis.get("skill_count", 0),
                "experience_level": analysis.get("experience_level", "N/A"),
                "domains": analysis.get("domains", []),
                "education": analysis.get("education", [])
            },
            "recommendations": format_recommendations(recommendations),
            "total_recommendations": len(recommendations)
        }), 200

    except Exception as e:
        print("Upload error:", e)
        return jsonify({
            "error": "Failed to process resume"
        }), 500

    finally:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)

# ----------------------------------
# Recommendation formatter (🔥 FIXED)
# ----------------------------------
def format_recommendations(recommendations):
    formatted = []

    for rec in recommendations:
        formatted.append({
            "course_id": rec.get("course_id", ""),
            "course_name": rec.get("course_name", "Unknown Course"),
            "instructor": rec.get("instructor", "Unknown"),
            "rating": rec.get("course_rating", 0),
            "platform": rec.get("platform", "Unknown"),
            "is_paid": rec.get("is_paid", "Unknown"),
            "enrolled": int(rec.get("Number_of_student_enrolled", 0)),
            "match_percentage": rec.get("match_percentage", 0),
            "match_reasons": rec.get("match_reasons", []),

            # ✅ SINGLE SOURCE OF TRUTH
            "course_url": extract_course_url(rec)
        })

    return formatted

# ----------------------------------
# Supporting APIs
# ----------------------------------
@app.route("/api/courses")
def get_courses():
    courses = course_manager.get_all_courses()
    return jsonify({"courses": courses, "total": len(courses)}), 200

@app.route("/api/course/<course_id>")
def get_course(course_id):
    course = course_manager.get_course_by_id(course_id)
    if course:
        return jsonify(course), 200
    return jsonify({"error": "Course not found"}), 404

@app.route("/api/search")
def search_courses():
    query = request.args.get("q", "")
    limit = request.args.get("limit", 10, type=int)
    results = course_manager.search_courses(query, limit)
    return jsonify({"results": results, "total": len(results)}), 200

@app.route("/api/stats")
def get_stats():
    return jsonify(course_manager.get_statistics()), 200

# ----------------------------------
# Error handlers
# ----------------------------------
@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large (max 16MB)"}), 413

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

# ----------------------------------
# Local run
# ----------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
