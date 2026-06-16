from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from askmarley.services.auth import (
    authenticate_user,
    get_current_user,
    login_user,
    logout_user,
    register_user,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if get_current_user():
        return redirect(url_for("main.home"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "consumer").strip()
        password = request.form.get("password", "")

        if not full_name or not email or not password:
            flash("Name, email, and password are required.", "error")
            return redirect(url_for("auth.register"))
        
        # Provider registration validation
        if role == "provider":
            company_name = request.form.get("company_name", "").strip()
            phone = request.form.get("phone", "").strip()
            business_reg_number = request.form.get("business_reg_number", "").strip()
            service_categories = request.form.getlist("service_categories")
            travel_postcodes = request.form.get("travel_postcodes", "").strip()
            insurance_verified = request.form.get("insurance_verified", "")
            
            if not company_name or not phone or not service_categories or not travel_postcodes:
                flash("Provider registration requires company name, phone, service categories, and travel postcodes.", "error")
                return redirect(url_for("auth.register"))
            
            ok, result = register_user(
                email, full_name, role, password,
                company_name=company_name,
                phone=phone,
                business_reg_number=business_reg_number,
                service_categories=service_categories,
                travel_postcodes=travel_postcodes,
                insurance_verified=insurance_verified,
            )
        else:
            consumer_phone = request.form.get("consumer_phone", "").strip()
            consumer_postcode = request.form.get("consumer_postcode", "").strip()
            
            if not consumer_postcode:
                flash("Postcode is required for consumer registration.", "error")
                return redirect(url_for("auth.register"))
            
            ok, result = register_user(
                email, full_name, role, password,
                consumer_phone=consumer_phone,
                consumer_postcode=consumer_postcode,
            )
        if not ok:
            flash(result, "error")
            return redirect(url_for("auth.register"))

        user = result
        login_user(user)
        flash("Account created and signed in.", "success")
        if user.role == "provider":
            return redirect(url_for("provider.dashboard"))
        return redirect(url_for("consumer.clipboard"))

    return render_template("auth_register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(url_for("main.home"))

    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "error")
            return redirect(url_for("auth.login"))

        user = authenticate_user(email, password)
        if not user:
            flash("Invalid credentials.", "error")
            return redirect(url_for("auth.login"))

        login_user(user)
        next_url = request.args.get("next")
        flash("Welcome back.", "success")
        if next_url:
            return redirect(next_url)
        if user.role == "provider":
            return redirect(url_for("provider.dashboard"))
        if user.role in {"admin", "super_admin"}:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("consumer.clipboard"))

    return render_template("auth_login.html")


@auth_bp.post("/logout")
def logout():
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("main.home"))


@auth_bp.post("/demo-login")
def demo_login():
    target = request.form.get("target", "consumer")
    email_map = {
        "consumer": "consumer.demo@askmarley.local",
        "provider": "provider.demo@askmarley.local",
        "admin": "admin@askmarley.local",
    }
    email = email_map.get(target, email_map["consumer"])
    user = authenticate_user(email, f"demo-{target}" if target != "admin" else "askmarley-admin")
    if not user:
        flash("Demo account is unavailable.", "error")
        return redirect(url_for("auth.login"))
    login_user(user)
    flash(f"Signed in as demo {target} account.", "success")
    if target == "provider":
        return redirect(url_for("provider.dashboard"))
    if target == "admin":
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("consumer.clipboard"))