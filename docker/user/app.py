#!/bin/env python3

# USERS.py
#   by Tim Müller
#
# Created:
#   07 Mar 2022, 14:40:28
# Last edited:
#   02 May 2023, 11:33:49
# Auto updated?
#   Yes
#
# Description:
#   Implements a simple microservice for managing users and user logins.
#   Build with the Flask (https://flask.palletsprojects.com/en/2.0.x/)
#   framework.
#

import base64
import binascii
import hashlib
import hmac
import json
import sys
import typing
import os

from flask import Flask, abort, request
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from utils import *


load_dotenv()


### CONSTANTS ###
# Secret to use when creating/validating JWTs
# Read ENV vars
JWT_SECRET = os.environ.get('JWT_SECRET')


### HELPER FUNCTIONS ###
def sign_jwt(message: str) -> str:
    """
        Generates a Base64-encoded signature of the given message string.

        The secret used is read from the `JWT_SECRET` global value.
    """

    # Now sign the header + payload
    signature = hmac.new(JWT_SECRET.encode("utf-8"), msg=message.encode("utf-8"), digestmod=hashlib.sha256).hexdigest()
    # Also encode it to Base64
    return base64.urlsafe_b64encode(signature.encode("utf-8")).decode("utf-8")


def generate_jwt(username: str) -> str:
    """
        Generates a new Json Web-Token (JWT) as specified in
        https://jwt.io/introduction/.

        Uses an HMAC SHA256 hashing algorithm to provide the token security.
        The secret is an arbitrary string stored as a constant; this is
        obviously not good practise in a production environment.

        Note that, as the defined, we use URL-safe Base64 encoding.
    """

    # Define the JSON header
    header = {
        "alg": "HS256",     # Pay attention this is correct for your algorithm used
        "typ": "JWT",
    }
    # Serialize it to Base64
    json_header = json.dumps(header)
    base64_header = base64.urlsafe_b64encode(json_header.encode("utf-8")).decode("utf-8")

    # Define the payload (the username only, to keep things simple)
    payload = {
        "sub": username
    }
    # Serialize it to Base64
    json_payload = json.dumps(payload)
    base64_payload = base64.urlsafe_b64encode(json_payload.encode("utf-8")).decode("utf-8")

    # Now sign the header + payload
    base64_signature = sign_jwt(f"{base64_header}.{base64_payload}")

    # Return the JWT!
    return f"{base64_header}.{base64_payload}.{base64_signature}"


def validate_jwt(token: str) -> typing.Optional[str]:
    """
        Validates the given JWT and, if it is valid, extracts its contents
        (i.e., the username).

        Essentially just extracts the username and re-creates that token to see
        if it's valid.

        If the input is invalid in any way, either because it is an invalid JWT
        or has an invalid signature, None is returned and the reason is printed
        to stderr for debugging purposes.
    """

    # Split the JWT on header/payload/signature
    parts = token.split('.')
    if len(parts) != 3:
        print(f"[debug] Invalidating token '{token}' because it has an invalid number of parts (got {len(parts)} != expected 3)", file=sys.stderr)
        return None

    # Now sign the piece of data and compare the signatures
    signature = sign_jwt(f"{parts[0]}.{parts[1]}")
    if parts[2] != signature:
        print(f"[debug] Invalidating token '{token}' because its signature does not match (got '{parts[2]}' != expected '{signature}')", file=sys.stderr)
        return None

    # The JWT was indeed generated by us, so let's retrieve the state (username)

    # Decode the Base64 of the body
    try:
        body = base64.urlsafe_b64decode(parts[1]).decode("utf-8")
    except binascii.Error as err:
        print(f"[debug] Invalidating token '{token}' because decoding it as Base64 failed: {err}", file=sys.stderr)
        print(f"[WARNING] The token is invalid, but its signature checks out; this should never happen! (has your secret been leaked?)", file=sys.stderr)
        return None

    # Decode the JSON of the body
    try:
        body = json.loads(body)
    except json.JSONDecodeError as err:
        print(f"[debug] Invalidating token '{token}' because decoding it as JSON failed: {err}", file=sys.stderr)
        print(f"[WARNING] The token is invalid, but its signature checks out; this should never happen! (has your secret been leaked?)", file=sys.stderr)
        return None

    # Finally, return the username if it exists
    if "sub" not in body:
        print(f"[debug] Invalidating token '{token}' because it does not have a 'sub' field", file=sys.stderr)
        print(f"[WARNING] The token is invalid, but its signature checks out; this should never happen! (has your secret been leaked?)", file=sys.stderr)
        return None
    return body["sub"]





### ENTRYPOINT ###
# Setup the application as a Flask app
app = Flask(__name__)


### API FUNCTIONS ###
# We use a flask macro to make let this function be called for the users URL ("/users") and the specified HTTP methods.
@app.route("/users", methods=['GET', 'POST', 'PUT'])
def users():
    """
        Handles managing users.

        Supported methods:
         - POST:   Create a new user with the given username, password pair.
                   Returns 200 on success, 403 if the user already exists or
                   400 if something went wrong.
         - DELETE: Deletes the given user - but only if the password was
                   correct. Returns 204 on success, 404 if the user does not
                   exist or 403 if the password was wrong.
    """
    if request.method == "GET":
        return "Hello, user", 200

    # Switch on the method used
    if request.method == "POST":
        # Try to get the username
        if "username" not in request.form:
            return "username not specified", 400
        username = request.form["username"]

        # Try to get the password
        if "password" not in request.form:
            return "password not specified", 400
        password = request.form["password"]

        try:
            result, status = create_user(username, password)
            if status:
                return "Sign up successful", 200
            if type(result) is dict:
                return "Username already exists", 409
            return "DB failed to execute query", 500
        except:
            return "Something went wrong", 500


    elif request.method == "PUT":
        # Try to get the username, old password and new password
        if "username" not in request.form:
            return "username not specified", 400
        username = request.form["username"]
        if "old-password" not in request.form:
            return "old-password not specified", 400
        old_password = request.form["old-password"]
        if "new-password" not in request.form:
            return "new-password not specified", 400
        new_password = request.form["new-password"]

        try:
            result, status = update_password(username, old_password, new_password)
            if status:
                return "Password update successful", 200
            if not type(result) is str:
                return "Update failed, incorrect password", 404
            return 'DB failed to execute query', 500
        except:
            return 'Something went wrong', 500
    

# We use a flask macro to make let this function be called for the login URL ("/users/login") and the specified HTTP methods.
@app.route("/users/login", methods=['POST'])
def login():
    """
        Handles logging users in or out.

        Supported methods:
         - POST: Tries to log the user in with the given username and password.
                 Returns 200 + the JWT on success, or a 403 otherwise.
    """

    # Switch on the method used
    if request.method == "POST":
        # Try to get the username
        if "username" not in request.form:
            return "username not specified", 400
        username = request.form["username"]

        # Try to get the password
        if "password" not in request.form:
            return "password not specified", 400
        password = request.form["password"]

        try:
            user, status = select_user_by_(username=username)
            if not user:
                return "Forbidden, no account", 403
            assert status
        except:
            return 'DB failed to execute query', 500
        
        if not check_password_hash(user['password'], password):
            return "Forbidden, incorrect password", 403

        # They are valid; create a JWT
        jwt = generate_jwt(username)

        # Done!
        return jwt, 200


# We use a flask macro to make let this function be called for the token validation endpoint ("/tokens") and the specified HTTP methods.
@app.route("/tokens", methods=['POST'])
def tokens():
    """
        Handles stuff with JWTs.

        Supported methods:
         - POST: Verifies the given JWT and returns the username contained
                 within if it is valid. Returns the name as a JSON string if the
                 token was valid, or else we return `null` (as JSON).
    """

    # Switch on the method used
    if request.method == "POST":
        # Try to get the JWT from the body
        if "token" not in request.form:
            return "token not specified", 400
        token = request.form["token"]

        # Validate it
        name = validate_jwt(token)
        if name is None:
            # Note that, at this point, the request did not fail; it did precisely what we asked it to do, which is deciding if the token is invalid or not.
            # Hence us returning 200, but using the body to indicate failure instead.
            return json.dumps(None), 200

        # Otherwise, return the name
        return json.dumps(name), 200
