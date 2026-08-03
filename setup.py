from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="gemini-client-api",
    version="1.0.0",
    author="Joy Saha",
    author_email="joysaha@example.com",
    description="A production-grade Python client & OpenAI-compatible REST API for Google's Gemini Web UI — Zero API Key Required.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/joy24-student/gemini.git",
    packages=find_packages(where=".", include=["gemini_client", "gemini_client.*"]),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.10",  # Uses asyncio.to_thread (3.9+) and dataclass slots=True (3.10+)
    install_requires=[
        "curl_cffi>=0.7.0",
        "httpx[http2]>=0.27.0",
        "pydantic>=2.0",
        "rich>=13.0",
        "requests>=2.31.0",
        "browser-cookie3>=0.20.1",
        "orjson>=3.9.0",
        "fastapi>=0.111.0",
        "uvicorn[standard]>=0.30.0",
    ],
    keywords="gemini google ai api client curl_cffi async joy-saha web-ui openai-compatible",
    project_urls={
        "Author Portfolio": "https://sahajoy.vercel.app/",
        "Source Code": "https://github.com/joy24-student/gemini.git",
        "Bug Reports": "https://github.com/joy24-student/gemini/issues",
    },
)
