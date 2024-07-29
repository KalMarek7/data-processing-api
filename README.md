# FastAPI Data Processing Backend

This FastAPI application was developed to help my team and me efficiently gather, process, construct, and convert raw API responses from our internal tools into useful reporting data. The application offers several endpoints, each designed to extract specific data or format it as needed:

-   **Automatic Data Extraction:** One endpoint performs automatic data extraction, triggered daily by external sources, and integrates with PowerBI reporting using Jupyter Notebook. Another one is also automatically triggered and sends the data as an email attachment.

-   **Manual Data Extraction:** Other endpoints handle manual, on-demand data extraction and conversion.

Essentially, this is an easy-to-deploy API that allows our team to make HTTP requests, eliminating the need for direct interaction with the tool's API endpoints. It improves efficiency by aggregating data from multiple sources and presenting it in more user-friendly formats. The application requires an API key for interaction and credentials for the tools, handling authorization against various APIs to deliver the requested data.

Please note that API keys, credentials, and parts of URLs have been redacted.

## Technologies used

-   **[Python](https://www.python.org/):** Python is a programming language that lets you work quickly and integrate systems more effectively.
-   **[FastAPI](https://fastapi.tiangolo.com/):** FastAPI is a modern, fast (high-performance), web framework for building APIs with Python based on standard Python type hints.
