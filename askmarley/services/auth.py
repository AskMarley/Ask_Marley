from functools import wraps

from flask import current_app, flash, has_app_context, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from askmarley.extensions import db
from askmarley.models import User

ROLE_ALIASES = {
    "consumer": "buyer",
    "buyer": "buyer",
    "provider": "seller",
    "seller": "seller",
    "admin": "admin",
    "super_admin": "super_admin",
}

LEGACY_STORAGE_ROLES = {
    "buyer": "consumer",
    "seller": "provider",
    "admin": "admin",
    "super_admin": "super_admin",
}

ALLOWED_SELF_REGISTER_ROLES = {"consumer", "provider", "buyer", "seller"}
ADMIN_ROLES = {"admin", "super_admin"}

DEFAULT_USERS = [
    {
        "email": "consumer.demo@askmarley.local",
        "full_name": "Demo Buyer",
        "role": "consumer",
        "consumer_tier": "individual",
        "password": "demo-consumer",
    },
    {
        "email": "provider.demo@askmarley.local",
        "full_name": "Demo Seller",
        "role": "provider",
        "consumer_tier": "free",
        "password": "demo-provider",
    },
    {
        "email": "admin@askmarley.local",
        "full_name": "Tolu",
        "role": "super_admin",
        "consumer_tier": "free",
        "password": "askmarley-admin",
    },
]


def normalize_role(role):
    return ROLE_ALIASES.get((role or "").strip().lower(), (role or "").strip().lower())


def _role_storage_mode():
    if has_app_context():
        mode = str(current_app.config.get("ROLE_STORAGE_MODE", "legacy")).strip().lower()
    else:
        mode = "legacy"
    return mode if mode in {"legacy", "canonical"} else "legacy"


def storage_role(role):
    normalized = normalize_role(role)
    if _role_storage_mode() == "canonical":
        return normalized
    return LEGACY_STORAGE_ROLES.get(normalized, normalized)


def role_matches(actual_role, *expected_roles):
    actual = normalize_role(actual_role)
    expected = {normalize_role(role) for role in expected_roles}
    return actual in expected

def ensure_default_users():
    for payload in DEFAULT_USERS:
        user = User.query.filter_by(email=payload["email"]).first()
        if not user:
            user = User(
                email=payload["email"],
                full_name=payload["full_name"],
                role=storage_role(payload["role"]),
                consumer_tier=payload["consumer_tier"],
                password_hash=generate_password_hash(payload["password"]),
            )
            db.session.add(user)
        elif not user.password_hash:
            user.password_hash = generate_password_hash(payload["password"])

    db.session.commit()


def get_current_user():
    auth_user = session.get("auth_user")
    user_id = session.get("auth_user_id")
    if not auth_user or not user_id:
        return auth_user

    user = db.session.get(User, user_id)
    if not user:
        return auth_user

    if user.account_disabled:
        session.pop("auth_user_id", None)
        session.pop("auth_user", None)
        session.modified = True
        return None

    refreshed = {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
    }
    session["auth_user"] = refreshed
    return refreshed


def is_authenticated():
    return get_current_user() is not None


def has_any_role(*roles):
    current = get_current_user()
    if not current:
        return False
    return role_matches(current.get("role"), *roles)


def login_user(user):
    auth_user = {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
    }
    session["auth_user_id"] = user.id
    session["auth_user"] = auth_user
    session.permanent = True
    session.modified = True
    return auth_user


def logout_user():
    session.pop("auth_user_id", None)
    session.pop("auth_user", None)
    session.modified = True


def register_user(email, full_name, role, password, **kwargs):
    normalized_email = email.strip().lower()
    if (role or "").strip().lower() not in ALLOWED_SELF_REGISTER_ROLES:
        return False, "Invalid account type."
    if User.query.filter_by(email=normalized_email).first():
        return False, "An account already exists for that email."

    stored_role = storage_role(role)

    user = User(
        email=normalized_email,
        full_name=full_name.strip(),
        role=stored_role,
        consumer_tier="individual" if role_matches(stored_role, "consumer") else "free",
        password_hash=generate_password_hash(password),
    )
    
    # Populate buyer fields if registering as buyer/consumer.
    if role_matches(stored_role, "consumer"):
        user.consumer_phone = kwargs.get("consumer_phone", "").strip()
        user.consumer_postcode = kwargs.get("consumer_postcode", "").strip()
    
    # Populate seller fields if registering as seller/provider.
    if role_matches(stored_role, "provider"):
        user.company_name = kwargs.get("company_name", "").strip()
        user.phone = kwargs.get("phone", "").strip()
        user.business_reg_number = kwargs.get("business_reg_number", "").strip()
        user.travel_postcodes = kwargs.get("travel_postcodes", "").strip()
        user.insurance_verified = kwargs.get("insurance_verified") == "true"
        user.provider_status = "pending"  # All new providers start pending verification
        
        # Join service categories from checkbox list
        service_categories = kwargs.get("service_categories", [])
        if isinstance(service_categories, list):
            user.service_categories = ",".join(service_categories)
        else:
            user.service_categories = service_categories
    
    db.session.add(user)
    db.session.commit()
    return True, user


def authenticate_user(email, password):
    normalized_email = email.strip().lower()
    user = User.query.filter_by(email=normalized_email).first()
    if not user:
        return None

    if not user.password_hash:
        return None

    if not check_password_hash(user.password_hash, password):
        return None

    if user.account_disabled:
        return None

    return user


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not is_authenticated():
            flash("Sign in to continue.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view_func(*args, **kwargs)

    return wrapped


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not is_authenticated():
                flash("Sign in to continue.", "warning")
                return redirect(url_for("auth.login", next=request.path))

            if not has_any_role(*roles):
                flash("Your account does not have access to that area.", "error")
                return redirect(url_for("main.home"))

            return view_func(*args, **kwargs)

        return wrapped

    return decorator