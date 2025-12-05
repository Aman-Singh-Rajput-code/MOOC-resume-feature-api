from flask import Flask, request, jsonify
import os
from werkzeug.utils import secure_filename
from config import Config
from models.course_manager import CourseManager
from models.resume_processor import ResumeProcessor
from models.recommendation_engine import RecommendationEngine
from flask_cors import CORS

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Enable CORS so MERN frontend can call this API
# In production, replace "*" with your frontend URL for security
CORS(app, resources={
    r"/api/*": {"origins": "*"},
    r"/upload": {"origins": "*"}
})

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize components (loaded once at startup)
print("Loading course data...")
course_manager = CourseManager()
print("Initializing resume processor...")
resume_processor = ResumeProcessor()
print("Initializing recommendation engine...")
recommendation_engine = RecommendationEngine(course_manager)
print("API service ready!")


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )


# =============================
#       HEALTH CHECK
# =============================

@app.route("/health", methods=["GET"])
def health():
    """Simple health check endpoint"""
    return jsonify({"status": "ok", "service": "mooc-resume-feature-api"}), 200


# =============================
#       MAIN API ENDPOINT
# =============================

@app.route("/upload", methods=["POST"])
def upload_resume():
    """
    API endpoint: upload resume and get recommendations

    Request:
      - Content-Type: multipart/form-data
      - Field: 'resume' -> PDF or DOCX

    Response (JSON):
      {
        "success": true,
        "analysis": {...},
        "recommendations": [...],
        "total_recommendations": 10
      }
    """

    # Check if file is present
    if "resume" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["resume"]

    # Check if file is selected
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    # Check if file type is allowed
    if not allowed_file(file.filename):
        return jsonify(
            {"error": "Invalid file type. Please upload PDF or DOCX"}
        ), 400

    filepath = None

    try:
        # Save file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        # Process resume
        analysis = resume_processor.process_resume(filepath)

        if not analysis:
            # Clean up file
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
            return (
                jsonify(
                    {
                        "error": "Failed to process resume. "
                                 "Please ensure it is a valid PDF or DOCX file"
                    }
                ),
                400,
            )

        # Generate recommendations
        recommendations = recommendation_engine.get_recommendations(analysis)

        # Clean up uploaded file (for privacy/security)
        if filepath and os.path.exists(filepath):
            os.remove(filepath)

        # Prepare response
        response_data = {
            "success": True,
            "analysis": {
                "skills": analysis.get("skills", [])[:20],  # Limit to 20
                "skill_count": analysis.get("skill_count", 0),
                "experience_level": analysis.get("experience_level", ""),
                "domains": analysis.get("domains", []),
                "education": analysis.get("education", []),
            },
            "recommendations": format_recommendations(recommendations),
            "total_recommendations": len(recommendations),
        }

        return jsonify(response_data), 200

    except Exception as e:
        # Clean up file if it exists
        if filepath and os.path.exists(filepath):
            os.remove(filepath)

        print(f"Error processing resume: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


def format_recommendations(recommendations):
    """Format recommendations for API response"""
    formatted = []

    for rec in recommendations:
        formatted.append(
            {
                "course_id": rec.get("course_id", ""),
                "course_name": rec.get("course_name", "Unknown Course"),
                "instructor": rec.get("instructor", "Unknown"),
                "rating": rec.get("course_rating", 0),
                "platform": rec.get("platform", "Unknown"),
                "is_paid": rec.get("is_paid", "Unknown"),
                "enrolled": int(rec.get("Number_of_student_enrolled", 0)),
                "match_percentage": rec.get("match_percentage", 0),
                "match_reasons": rec.get("match_reasons", []),
                "sources": rec.get("sources", []),
            }
        )

    return formatted


# =============================
#       SUPPORTING APIs
# =============================

@app.route("/api/courses", methods=["GET"])
def get_courses():
    """API endpoint to get all courses"""
    courses = course_manager.get_all_courses()
    return jsonify({"courses": courses, "total": len(courses)}), 200


@app.route("/api/course/<course_id>", methods=["GET"])
def get_course(course_id):
    """API endpoint to get specific course"""
    course = course_manager.get_course_by_id(course_id)
    if course:
        return jsonify(course), 200
    return jsonify({"error": "Course not found"}), 404


@app.route("/api/search", methods=["GET"])
def search_courses():
    """API endpoint to search courses"""
    query = request.args.get("q", "")
    limit = request.args.get("limit", 10, type=int)

    results = course_manager.search_courses(query, limit)
    return jsonify({"results": results, "total": len(results)}), 200


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """API endpoint to get dataset statistics"""
    stats = course_manager.get_statistics()
    return jsonify(stats), 200


# =============================
#         ERROR HANDLERS
# =============================

@app.errorhandler(413)
def too_large(e):
    """Handle file too large error"""
    return jsonify({"error": "File too large. Maximum size is 16MB"}), 413


@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors (API style)"""
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors"""
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    # For local testing; Render uses gunicorn from Procfile
    app.run(debug=True, host="0.0.0.0", port=5000)
