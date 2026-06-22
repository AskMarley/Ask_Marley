from flask import Blueprint, jsonify, render_template

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def home():
    return render_template("index.html")


@main_bp.get("/privacy-policy")
def privacy_policy():
    return render_template("privacy_policy.html")


@main_bp.get("/terms-and-conditions")
def terms_and_conditions():
    return render_template("terms_and_conditions.html")


@main_bp.get("/health")
def health():
    return jsonify({"status": "ok"})
