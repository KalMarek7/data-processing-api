import requests
from time import sleep
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

live_agents = {
    "devdev": 29,
    "tenant1": 22,
    "tenant1dev": 21,
    "tenant2": 20,
    "tenant2dev": 20,
    "tenant3": 15,
    "tenant3dev": 16,
    "tenant4": 99,
    "tenant4dev": 14
}


def chatbot_auth(tenant: str, CREDS: str) -> str:
    username = CREDS.split("||")[0]
    password = CREDS.split("||")[1]
    url = f"https://{tenant}.esp.com/api/authentication/auth/login/"
    payload = {
        "username": username,
        "password": password
    }
    response = requests.post(url, json=payload)
    print("Post to authenticate...")
    if response.status_code == 200:
        global token
        data = response.json()
        token = data["key"]
        print("Succes. Got token")
        return token
    else:
        print(
            f"Error in chatbot_auth: {response.status_code} - {response.text}")
        return "FAILED TO GET TOKEN"


def get_graphql(tenant: str, CREDS: str, filter: dict) -> dict:
    token = chatbot_auth(tenant, CREDS)
    url = f"https://{tenant}.esp.com/api/graph/"
    headers = {
        'Content-Type': 'application/json',
        "Authorization": f"Token {token}"
    }
    query = """query getInteractions($interactionFilter: InteractionFilter!){
    interactions(
      filters: $interactionFilter
      ){
        pageInfo {
            hasNextPage
            hasPreviousPage
            startCursor
            endCursor
        }
        channelCounts{
            name
            count
        }
 
        edges{  
            node{
                    creation {
                    date
                    }
                    eid
                    interactionText
                    cleanInteractionText
                    noResponse
                    userName
                    userJobRole
                    userDepartment
                    userLocation
                    city
                    state
                    country
                    matchedArchetypeIntent
                    actualMatchedIntent
                    actualMatchedApplication
                    actualMatchedApplicationType
                    intentReviewed
                    source
                    caseReference
                    espServiceDepartment
                    espCategory
                    espServiceTeam
                    serviceDepartment
                    serviceDepartmentClassification
                    helpfulFeedback
                    taskFeedback
                    supportFeedback
                    deflected
                    possiblyAbandoned
                    channel
                    os
                    client
                    isoCountryCode
                    conversationChannel
                    kbResponse
                    userLanguage
                    actualMatchedIntentReportingLabel
                    matchedArchetypeIntentReportingLabel
                    severity
                    keywords
                    automationStatus  
            }  
        }
        keywordCounts {
            name
            count
        }
    }
}"""
    variables = {
        "interactionFilter": filter
    }
    payload = {
        'query': query,
        'variables': variables
    }
    print(f"Filter: {filter}")
    print("Making request to GraphQL API...")
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        print("Success. Got data")
        data = response.json()
        for i in range(len(data['interactions']['channelCounts'])):
            print(
                f"{data['interactions']['channelCounts'][i]['name']}: {data['interactions']['channelCounts'][i]['count']}")
        return {"data": data, "token": token}
    else:
        print(
            f"Error in get_graphql: {response.status_code} - {response.text}")
        return {"error": f"{response.status_code} - {response.text}"}


def process_graphql(data: dict) -> list:
    non_deflected = []
    deflected = []
    others = []

    for i in data["interactions"]["edges"]:
        if i["node"]["deflected"] == False:
            non_deflected.append(i["node"])
        elif i["node"]["deflected"] == True:
            deflected.append(i["node"])
        else:
            others.append(i["node"])

    seen_conversations = {}
    for i in non_deflected:
        seen_conversations.setdefault(i["conversationChannel"], i)
    unique_conversations = list(seen_conversations.values())

    print(f"All interactions length: {len(data['interactions']['edges'])}")
    print(f"Non-deflected interactions length: {len(non_deflected)}")
    print(f"Deflected interactions length: {len(deflected)}")
    print(f"Other interactions length: {len(others)}")
    print(
        f"Unique non-deflected conversations length: {len(unique_conversations)}")
    print(f"Processing {len(unique_conversations)} items...")

    return unique_conversations


class Conv():
    def __init__(self, count: int, conversation: dict, job_id: str, tenant: str, token: str):
        for key, value in conversation.items():
            self.__setattr__(key, value)

        conv_id = self.__getattribute__("conversationChannel")
        url = f"https://{tenant}.esp.com/api/chat/v0.1/admin_channels/{
            conv_id}/messages/?format=json&limit=200"
        headers = {"Authorization": f"Token {token}"}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            self.__setattr__("events", [i for i in reversed(data["results"])])
            print(f"[{job_id}] {count}. Getting conversation {conv_id}")
            self.get_transcript(tenant)
        else:
            print(
                f"Error in Conv__init__: {response.status_code} - {response.text}")

    def get_transcript(self, tenant: str):
        live_agent_id = live_agents[tenant]
        string = ""
        for i in self.__getattribute__("events"):
            if i["type"] == "message":
                if i["user_id"] == 1:
                    sender = "chatbot"
                elif i["user_id"] == live_agent_id:
                    sender = "Live Agent"
                else:
                    sender = self.__getattribute__("userName")
                string += f"{sender}:\n{i['text']}\n\n"

        self.__setattr__("transcript", string)
        print("Transcript added")
        self.__delattr__("events")

    def to_dict(self):
        return self.__dict__


def get_messages(tenant: str, CREDS: str, conversation_id: str) -> str:
    url = f"https://{tenant}.esp.com/api/chat/v0.1/admin_channels/{
        conversation_id}/messages/?format=json&limit=300"
    token = chatbot_auth(tenant, CREDS)
    headers = {
        "Authorization": f"Token {token}"
    }
    print("Getting messages...")
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print(f"Got conversation {conversation_id}")
        data = response.json()
        if data["count"] == 0:
            raise IndexError(f"No results for {conversation_id}")
        else:
            return get_transcript(tenant, data)
    else:
        raise Exception(f"Error: {response.status_code} - {response.text}")


def get_transcript(tenant: str, data: dict) -> str:
    live_agent_id = live_agents[tenant]
    transcript = ""
    for i in reversed(data["results"]):
        if i["type"] == "message":
            if i["user_id"] != 1 and i["user_id"] != live_agent_id:
                user = get_user_from_id(tenant, token, i["user_id"])
                break

    for i in reversed(data["results"]):
        if i["type"] == "message":
            if i["user_id"] == 1:
                sender = "chatbot"
            elif i["user_id"] == live_agent_id:
                sender = "Live Agent"
            else:
                sender = user
            transcript += f"{sender}:\n{i['text']}\n\n"

    return transcript


def get_user_from_id(tenant: str, token: str, user_id: int) -> str:
    print("Getting user...")
    url = f"https://{tenant}.esp.com/api/espuser/v0.1/users/{user_id}/"
    headers = {
        "Authorization": f"Token {token}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data["full_name"]
    else:
        raise Exception(f"Error: {response.status_code} - {response.text}")


def get_exporting_data(tenant: str, CREDS: str, resource: str) -> list:

    match resource:
        case "configuration":
            url = f"https://{tenant}.esp.com/api/config/v0.1/configuration/?limit=200&format=json"
        case "variables":
            url = f"https://{tenant}.esp.com/api/chatbot/v0.1/variables/?limit=200&format=json"
        case "localization":
            url = f"https://{tenant}.esp.com/api/common/v0.1/localization?limit=200&format=json"
        case "kb_support":
            url = f"https://{tenant}.esp.com/api/chatbot/v0.1/kb_support/?limit=200&format=json"

    token = chatbot_auth(tenant, CREDS)
    headers = {
        "Authorization": f"Token {token}"
    }
    data = make_requests(url, headers, True, [])
    return data


def make_requests(url: str, headers: dict, initial_request: bool, full_data: list) -> list:
    if not initial_request:
        sleep(1)

    if url != None:
        print("Making request...")
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            print("Got data")
            json_data = r.json()
            if initial_request:
                print(f"Items count: {json_data['count']}")
            for i in json_data["results"]:
                full_data.append(i)
            if json_data["next"] == None:
                return full_data
            else:
                return make_requests(json_data["next"], headers, False, full_data)
        else:
            print(f"Error in make_requests: {r.status_code} - {r.text}")
            return ["ERROR"]
    else:
        return full_data


def get_surveys(CREDS: str, today, yesterday) -> bytes | str:
    token = chatbot_auth("tenant", CREDS)
    url = f"https://tenant.esp.com/api/chatbot/v0.1/report9_data/csv/?end_date={
        yesterday}&esp_filters=live_chat_interaction_feedback__!ISNULL%3DTrue&header=conversation_channel%2Csys_date_created%2Cinteraction_text%2Ccase_reference%2Cuser_name%2Cactual_matched_intent%2Cesp_service_department%2Csource%2Cno_response%2Cdeflected%2Ckb_response%2Chelpful_feedback%2Cpossibly_abandoned%2Clive_chat_interaction_feedback&start_date={yesterday}&format=json"
    headers = {
        "Authorization": f"Token {token}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print("Success. Job started")
        data = response.json()
        print(data["status"])
        status_url = data["url"] + "&format=json"
        print(status_url)
        print("Waiting 30 seconds")
        sleep(30)
        download_url = get_download_url(token, status_url)
        survey_data = download_data(token, download_url)
        return survey_data
    else:
        print(f"{response.status_code} - {response.text}")
        return f"{response.status_code} - {response.text}"


def get_download_url(token: str, url: str) -> str:
    headers = {
        "Authorization": f"Token {token}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print("Success. Got download url")
        data = response.json()
        print(data["status"])
        download_url = data["sys_custom_fields"]["file"]
        return download_url
    else:
        print(f"{response.status_code} - {response.text}")
        return f"{response.status_code} - {response.text}"


def download_data(token: str, url: str) -> bytes | str:
    headers = {
        "Authorization": f"Token {token}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print("Success. Got data")
        print(f"Type of data: {type(response.content)}")
        return response.content
    else:
        print(f"{response.status_code} - {response.text}")
        return f"{response.status_code} - {response.text}"


def send_email(connection: str, credentials: str, email: str, data: bytes, yesterday, filename: str) -> None:
    print("Sending email")
    host = connection.split(":")[0]
    port = int(connection.split(":")[1])
    username = credentials.split("||")[0]
    password = credentials.split("||")[1]
    sender = f"AVA Team Reports <{username}>"
    receiver = email.split("||")
    subject = f"Feedback {yesterday}"
    body = f"Hello,\n\nAttached is Feedback Survey for {yesterday}"

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender
    msg.attach(MIMEText(body, "plain"))

    attachment = MIMEApplication(data, Name=filename)
    attachment["Content-Disposition"] = f"attachment; filename={filename}"
    msg.attach(attachment)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(username, password)
        server.sendmail(sender, receiver, msg.as_string())
        server.quit()
        print("Email sent")
