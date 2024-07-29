from ava import get_graphql, process_graphql, Conv, get_messages, get_exporting_data, get_surveys, send_email
import logging
import sys
import os
import csv
import io
import uuid
from time import sleep
from datetime import datetime, timedelta
from openpyxl import Workbook
from fastapi import FastAPI, BackgroundTasks, Header, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse

API_KEY = os.getenv("API_KEY")
CREDS = os.getenv("CREDS")
LOG_MODE = os.getenv("LOG_MODE")

SMTP_CONN = os.getenv("SMTP_CONN")
SMTP_CREDS = os.getenv("SMTP_CREDS")
MAIL_TO = os.getenv("MAIL_TO")

valid_tenants = ["devdev", "tenant1", "tenant1dev", "tenant2",
                 "tenant2dev", "tenant3", "tenant3dev", "tenant4", "tenant4dev"]

if not API_KEY:
    raise EnvironmentError("API_KEY environment variable not set")

if not CREDS:
    raise EnvironmentError("CREDS environment variable not set")

if LOG_MODE != None and LOG_MODE != "debug":
    raise EnvironmentError("LOG_MODE can only be 'debug")

if not SMTP_CONN:
    raise EnvironmentError("SMTP_CONN environment variable not set")

if not SMTP_CREDS:
    raise EnvironmentError("SMTP_CREDS environment variable not set")

if not MAIL_TO:
    raise EnvironmentError("MAIL_TO environment variable not set")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stdout))


def authenticate(x_api_key: str = Header(None, title="API Key", description="Your API Key")) -> bool:
    if x_api_key is None or x_api_key != API_KEY:
        raise HTTPException(
            status_code=401, detail="Missing or invalid API key"
        )
    return True


async def verify_tenant(request: Request) -> bool:
    try:
        body = await request.json()
        tenant = body["tenant"]
    except:
        raise HTTPException(
            status_code=400, detail="'tenant' key missing from request body")

    if tenant not in valid_tenants:
        raise HTTPException(
            status_code=403, detail=f"Tenant '{tenant}' not supported")

    return True


async def verify_conversation_id(request: Request) -> bool:
    try:
        body = await request.json()
        tenant = body["tenant"]
    except:
        raise HTTPException(
            status_code=400, detail="'tenant' key missing from request body")

    if tenant not in valid_tenants:
        raise HTTPException(
            status_code=403, detail=f"Tenant '{tenant}' not supported")

    try:
        body = await request.json()
        conversation_id = body["conversation_id"]
    except:
        raise HTTPException(
            status_code=400, detail="'conversation_id' key missing from request body")

    return True


def list_of_dicts_to_csv_stringio(data: list[dict]) -> io.StringIO:
    buffer = io.StringIO()

    writer = csv.DictWriter(buffer, fieldnames=data[0].keys())
    writer.writeheader()
    for d in data:
        writer.writerow(d)

    # Go back to the start of the StringIO object to get the CSV data
    buffer.seek(0)
    return buffer


def process_reporting_data_and_update_job(job_id: str, data: dict, tenant: str, token: str) -> None:
    list_of_convs = []
    results = []
    for index, item in enumerate(process_graphql(data)):
        list_of_convs.append(Conv(index + 1, item, job_id, tenant, token))
        results.append(list_of_convs[index].to_dict())
        # print("ZzzZZ...")
        sleep(1)

    print(f"Done. Processed {len(results)} items")

    # Generate the CSV data
    try:
        buffer = list_of_dicts_to_csv_stringio(results)
        jobs[job_id]["status"] = "completed"
        # Store the CSV data as a string
        jobs[job_id]["data"] = buffer.getvalue()
    except IndexError:
        print("Stopping job, no items to process")
        del jobs[job_id]


def get_surveys_and_send_email(job_id: str, CREDS: str) -> None:
    today = datetime.today().date()
    yesterday = today - timedelta(days=1)
    filename = f"live_chat_interaction_feedback_{yesterday}.csv"
    data = get_surveys(CREDS, today, yesterday)
    print("Done. Got the surveys")
    send_email(SMTP_CONN, SMTP_CREDS, MAIL_TO, data, yesterday, filename)
    del jobs[job_id]


app = FastAPI()
# In-memory storage for job statuses and results
jobs: dict[str, dict] = {}


# root
@app.get("/")
async def read_root(request: Request, api_key: bool = Depends(authenticate)) -> dict:
    if LOG_MODE:
        logger.info(f"Headers:\n${request.headers}")

    return {"message": "Welcome to AVA Team API", "memory": f"{len(jobs.keys())} jobs: {list(jobs.keys())}"}


# reporting
@app.post("/reporting/start_job/")
async def start_job(background_tasks: BackgroundTasks, request: Request, api_key: bool = Depends(authenticate), body=Depends(verify_tenant)) -> dict:
    if LOG_MODE:
        logger.info(f"Headers:\n${request.headers}")

    body = await request.json()
    tenant = body["tenant"]
    print(tenant)

    try:
        filter = body["filter"]
    except:
        filter = {"createdDateRange": ["2024-03-25", "2024-03-31"]}

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing"}

    result_object = get_graphql(tenant, CREDS, filter)
    csv_data = result_object["data"]
    token = result_object["token"]

    background_tasks.add_task(
        process_reporting_data_and_update_job, job_id, csv_data, tenant, token)
    return {"job_id": job_id}


@app.get("/reporting/job_status/{job_id}/")
async def get_status(job_id: str, request: Request, api_key: bool = Depends(authenticate)) -> dict:
    if LOG_MODE:
        logger.info(f"Headers:\n${request.headers}")
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job_status = jobs[job_id]["status"]
    return {"status": job_status}


@app.get("/reporting/download/{job_id}/")
async def download_csv(job_id: str, request: Request, api_key: bool = Depends(authenticate)) -> StreamingResponse:
    if LOG_MODE:
        logger.info(f"Headers:\n${request.headers}")
    if job_id not in jobs:
        raise HTTPException(
            status_code=404, detail="Job not found or still processing")
    if jobs[job_id]["status"] == "processing":
        raise HTTPException(
            status_code=425, detail="Too early, still processing job")

    csv_data = jobs[job_id]["data"]

    # Create a generator to stream the CSV data
    def iterfile():
        buffer = io.StringIO(csv_data)
        yield from buffer

    # Create a streaming response to stream the CSV data
    response = StreamingResponse(
        iterfile(), media_type="text/csv")

    # Add a Content-Disposition header to prompt the file download
    response.headers["Content-Disposition"] = f"attachment; filename={
        job_id}.csv"

    # Clean memory
    del jobs[job_id]

    return response


# pbi
@app.post("/pbi/start_job/")
async def start_pbi_job(background_tasks: BackgroundTasks, request: Request, api_key: bool = Depends(authenticate), body=Depends(verify_tenant)) -> dict:
    if LOG_MODE:
        logger.info(f"Headers:\n${request.headers}")

    today = datetime.today().date()
    yesterday = today - timedelta(days=1)

    body = await request.json()
    tenant = body["tenant"]
    print(f"PBI JOB for {tenant}")

    try:
        filter = body["filter"]
    except:
        filter = {"createdDateRange": [f"{yesterday}", f"{today}"]}

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"is_scheduled": True,
                    "status": "processing", "tenant": tenant}

    result_object = get_graphql(tenant, CREDS, filter)
    csv_data = result_object["data"]
    token = result_object["token"]

    background_tasks.add_task(
        process_reporting_data_and_update_job, job_id, csv_data, tenant, token)
    return {"job_id": job_id, "is_scheduled": jobs[job_id]["is_scheduled"], "tenant": tenant}


@app.get("/pbi/download/")
async def download_pbi_csv(request: Request, api_key: bool = Depends(authenticate), body=Depends(verify_tenant)) -> StreamingResponse:
    if LOG_MODE:
        logger.info(f"Headers:\n${request.headers}")

    body = await request.json()
    tenant = body["tenant"]

    job_id = ""
    for id, job_info in jobs.items():
        if "tenant" in job_info and job_info["tenant"] == tenant:
            job_id = id

    if job_id == "":
        raise HTTPException(status_code=403, detail=f"No jobs for '{tenant}'")

    if jobs[job_id]["status"] == "processing":
        raise HTTPException(
            status_code=425, detail="Too early, still processing job")

    csv_data = jobs[job_id]["data"]

    # Create a generator to stream the CSV data
    def iterfile():
        buffer = io.StringIO(csv_data)
        yield from buffer

    # Create a streaming response to stream the CSV data
    response = StreamingResponse(
        iterfile(), media_type="text/csv")

    # Add a Content-Disposition header to prompt the file download
    response.headers["Content-Disposition"] = f"attachment; filename={
        job_id}.csv"

    # Clean memory
    del jobs[job_id]

    return response


# exporting
@app.post("/exporting/transcript/")
async def start_transcript(request: Request, api_key: bool = Depends(authenticate), body=Depends(verify_conversation_id)) -> StreamingResponse:
    if LOG_MODE:
        logger.info(f"Headers:\n${request.headers}")

    body = await request.json()
    tenant = body["tenant"]
    conversation_id = body["conversation_id"]
    print(body["tenant"])

    try:
        transcript = get_messages(tenant, CREDS, conversation_id)
        print("Returning data...")
    except IndexError:
        print(f"404 - Conversation {conversation_id} not found")
        raise HTTPException(
            status_code=404, detail=f"Conversation {conversation_id} not found")
    except Exception:
        print(
            f"Conversation id: '{conversation_id}' is in wrong format or ESP API error")
        raise HTTPException(
            status_code=400, detail=f"Conversation id: '{conversation_id}' is in wrong format or ESP API error")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing"}

    # Create a generator to stream the CSV data
    def iterfile():
        buffer = io.StringIO(transcript)
        yield from buffer

    # Create a streaming response to stream the CSV data
    response = StreamingResponse(
        iterfile(), media_type="text/csv")

    # Add a Content-Disposition header to prompt the file download
    response.headers["Content-Disposition"] = f"attachment; filename={
        tenant}_{conversation_id}_transcript.txt"

    # Clean memory
    del jobs[job_id]

    return response


@app.post("/exporting/{resource}/")
async def start_exporting_job(resource: str, request: Request, api_key: bool = Depends(authenticate), body=Depends(verify_tenant)) -> StreamingResponse:
    if LOG_MODE:
        logger.info(f"Headers:\n${request.headers}")

    available_resources = ["configuration",
                           "variables", "localization", "kb_support"]
    if resource not in available_resources:
        raise HTTPException(
            status_code=404, detail=f"Resource {resource} not available for exporting.")

    body = await request.json()
    tenant = body["tenant"]
    print(body["tenant"])
    print(resource)

    data = get_exporting_data(tenant, CREDS, resource)
    print("Returning data...")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing"}

    # Create an in-memory bytes buffer
    output = io.BytesIO()

    # Create an XLSX file in the buffer
    wb = Workbook()
    ws = wb.active
    headers = data[0].keys()
    ws.append(list(headers))
    # Write data rows
    for row in data:
        row_values = [str(value) for value in row.values()]
        ws.append(row_values)

    # Save the workbook to the buffer
    wb.save(output)
    # Seek to the start of the BytesIO buffer
    output.seek(0)

    # Clean memory
    del jobs[job_id]

    # Create a StreamingResponse to stream the XLSX file
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={tenant}_{resource}.xlsx"})


@app.post("/surveys/")
async def start_surveys_job(background_tasks: BackgroundTasks, request: Request, api_key: bool = Depends(authenticate)) -> dict:
    if LOG_MODE:
        logger.info(f"Headers:\n${request.headers}")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing"}
    background_tasks.add_task(
        get_surveys_and_send_email, job_id, CREDS)
    return {"job_id": job_id}
