# -*- coding: utf-8 -*-
import json
from pathlib import Path
from typing import Dict, Tuple, Union, Optional

from curl_cffi import CurlError
from curl_cffi.requests import AsyncSession
from requests.exceptions import RequestException, HTTPError, Timeout # Added Timeout

from rich.console import Console

# Assuming Endpoint and Headers enums are in 'enums.py' within the same package
from .enums import Endpoint, Headers

console = Console() # Instantiate console for logging

async def upload_file(
    file: Union[bytes, str, Path],
    proxy: Optional[Union[str, Dict[str, str]]] = None,
    impersonate: str = "chrome110",
    cookies: Optional[Dict[str, str]] = None,
) -> str:
    """
    Uploads a file to Google's Gemini server using curl_cffi and returns its identifier.

    Args:
        file (bytes | str | Path): File data in bytes or path to the file to be uploaded.
        proxy (str | dict, optional): Proxy URL or dictionary for the request.
        impersonate (str, optional): Browser profile for curl_cffi to impersonate. Defaults to "chrome110".
        cookies (dict, optional): Cookies for authentication with Google upload endpoint.

    Returns:
        str: Identifier of the uploaded file.

    Raises:
        HTTPError: If the upload request fails.
        RequestException: For other network-related errors.
        FileNotFoundError: If the file path does not exist.
    """
    # Handle file input
    if not isinstance(file, bytes):
        file_path = Path(file)
        if not file_path.is_file():
            raise FileNotFoundError(f"File not found at path: {file}")
        with open(file_path, "rb") as f:
            file_content = f.read()
    else:
        file_content = file

    # Prepare proxy dictionary for curl_cffi
    proxies_dict = None
    if isinstance(proxy, str):
        proxies_dict = {"http": proxy, "https": proxy} # curl_cffi uses http/https keys
    elif isinstance(proxy, dict):
        proxies_dict = proxy # Assume it's already in the correct format

    try:
        import httpx
        # Build httpx-compatible proxy: str for simple URL, None otherwise (dict proxies go via mounts)
        httpx_proxy = proxy if isinstance(proxy, str) else (list(proxies_dict.values())[0] if proxies_dict else None)
        # Update headers with Content-Type required by Gemini upload endpoint
        upload_headers = Headers.UPLOAD.value.copy()
        async with httpx.AsyncClient(
            proxy=httpx_proxy,
            headers=upload_headers,
            cookies=cookies,
            timeout=30.0,
        ) as client:
            response = await client.post(
                url=Endpoint.UPLOAD.value,
                files={"file": ("image.jpg", file_content, "image/jpeg")},
            )
            response.raise_for_status()
            clean_id = response.text.replace("'", "").replace('"', "").strip()
            return clean_id
    except HTTPError as e:
        console.log(f"[red]HTTP error during file upload: {e.response.status_code} {e}[/red]")
        raise # Re-raise HTTPError
    except (RequestException, CurlError) as e: # Catch CurlError as well
        console.log(f"[red]Network error during file upload: {e}[/red]")
        raise # Re-raise other request errors

def load_all_cookies(cookie_path: str) -> Dict[str, str]:
    """
    Loads all cookies from a JSON file as a dictionary.
    Supports both dict format ({"name": "val"}) and browser export list format ([{"name": "...", "value": "..."}]).
    """
    try:
        with open(cookie_path, 'r', encoding='utf-8') as file:
            data = json.load(file)

        cookies = {}
        if isinstance(data, dict):
            for k, v in data.items():
                cookies[str(k)] = str(v)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "name" in item and "value" in item:
                    cookies[str(item["name"])] = str(item["value"])

        return cookies
    except Exception:
        return {}


def save_cookies(cookies: Dict[str, str], cookie_path: str = "cookies.json") -> None:
    """
    Saves or updates cookie dictionary to a JSON file.
    Preserves list-of-dicts format if existing file is a list, or writes dict format cleanly.
    """
    if not cookies or not cookie_path:
        return

    try:
        path = Path(cookie_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing_data = None
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except Exception:
                pass

        if isinstance(existing_data, list):
            # Update list format
            updated_list = []
            updated_names = set()
            for item in existing_data:
                if isinstance(item, dict) and "name" in item:
                    name = str(item["name"])
                    if name in cookies:
                        item["value"] = cookies[name]
                        updated_names.add(name)
                    updated_list.append(item)
            for k, v in cookies.items():
                if k not in updated_names:
                    updated_list.append({"name": k, "value": v})
            out_data = updated_list
        else:
            # Dict format
            out_data = dict(cookies)
            if isinstance(existing_data, dict):
                out_data = {**existing_data, **cookies}

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out_data, f, indent=2)
    except Exception as e:
        console.log(f"[yellow]Failed to save updated cookies to {cookie_path}: {e}[/yellow]")


def load_cookies(cookie_path: str) -> Tuple[str, str]:
    """
    Loads authentication cookies from a JSON file (supports both dict and browser export list formats).

    Args:
        cookie_path (str): Path to the JSON file containing cookies.

    Returns:
        tuple[str, str]: Tuple containing __Secure-1PSID and __Secure-1PSIDTS cookie values.
    """
    try:
        with open(cookie_path, 'r', encoding='utf-8') as file:
            data = json.load(file)

        psid = ""
        psidts = ""
        if isinstance(data, dict):
            for k, v in data.items():
                if k.upper() == "__SECURE-1PSID":
                    psid = str(v)
                elif k.upper() == "__SECURE-1PSIDTS":
                    psidts = str(v)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    name = str(item.get("name", ""))
                    val = str(item.get("value", ""))
                    if name.upper() == "__SECURE-1PSID":
                        psid = val
                    elif name.upper() == "__SECURE-1PSIDTS":
                        psidts = val

        if not psid:
            raise ValueError("Required cookie __Secure-1PSID not found in cookie file.")

        return psid, psidts

    except FileNotFoundError:
        raise Exception(f"Cookie file not found at path: {cookie_path}")
    except json.JSONDecodeError:
        raise Exception("Invalid JSON format in the cookie file.")
    except Exception as e:
        raise Exception(f"Error loading cookies from {cookie_path}: {e}")


def ensure_data_dir(subdir: str = "") -> Path:
    """
    Returns a writable directory Path for storage.
    First tries user home directory (~/.gemini/<subdir>).
    If user home is read-only (e.g., Vercel, AWS Lambda, Docker read-only container),
    falls back to system temporary directory (/tmp/.gemini/<subdir>).
    """
    import tempfile
    try:
        path = Path.home() / ".gemini"
        if subdir:
            path = path / subdir
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        path = Path(tempfile.gettempdir()) / ".gemini"
        if subdir:
            path = path / subdir
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return path

