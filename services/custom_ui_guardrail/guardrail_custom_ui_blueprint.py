from app.main import app  # noqa: F401  re-exported for uvicorn


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")


if __name__ == "__main__":
    main()
