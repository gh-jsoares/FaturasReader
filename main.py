from __future__ import print_function
import os
import sys
import slate3k as slate
import datetime
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/calendar']


def formatDateTime(time):
    return time.strftime("%Y-%m-%dT00:00:00+00:00")


def createEvent(service, title, description, start):
    end = start + datetime.timedelta(days=1)
    EVENT = {
        'summary': title,
        'description': description,
        'start': {
            'dateTime': formatDateTime(start),
            'timeZone': 'Europe/Lisbon',
        },
        'end': {
            'dateTime': formatDateTime(end),
            'timeZone': 'Europe/Lisbon',
        },
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},  # day before
                {'method': 'popup', 'minutes': 24 * 60},  # day before
                {'method': 'email', 'minutes': 30},  # 30 mins
                {'method': 'popup', 'minutes': 30},  # 30 mins
            ]
        }
    }

    event = service.events().insert(calendarId='primary', body=EVENT,
                                    sendNotifications=True).execute()
    return event.get('htmlLink')


def initializeGoogleApi():
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    try:
        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        service = build('calendar', 'v3', credentials=creds,
                        cache_discovery=False)
    except:
        sys.exit("An error occurred with the Google Calendar API")

    return service


def readPdf(path, page=0):
    file = open(path, 'rb')
    return list(filter(lambda x: x.strip() != '', slate.PDF(file)[page].split("\n")))


def parseTime(time):
    return datetime.datetime.strptime(time, "%d-%m-%Y")


def extractGold(path):
    lines = readPdf(path)
    ref_index = lines.index("REFERÊNCIA") - 1
    ref = lines[ref_index].strip()
    ent = lines[lines.index("ENTIDADE", ref_index) - 1].strip()
    mon = lines[lines.index("MONTANTE", ref_index) - 1].strip()
    date = lines[-2].strip()
    date = "".join([c if c.isalnum() else "-" for c in date])

    def last_day_of_month(any_day):
        next_month = any_day.replace(day=28) + datetime.timedelta(days=4)
        return next_month - datetime.timedelta(days=next_month.day)
    leitura = last_day_of_month(parseTime(date)).strftime("%d-%m-%Y")
    return {'REFERÊNCIA': ref, 'ENTIDADE': ent, 'MONTANTE': mon, 'DATA LIMITE': date, 'PRÓXIMA LEITURA': leitura}


def extractEpal(path):
    lines = readPdf(path)
    index = lines.index("PARA PAGAMENTO EM AGENTES") + 1
    ent = lines[index].strip()
    ref = lines[index + 1].strip()
    mon = lines[index + 2].strip()

    def fixDate(date):
        return "-".join(reversed("".join([c if c.isalnum()
                                          else "-" for c in date]).split('-')))

    date = fixDate(lines[lines.index("DATA LIMITE DE PAGAMENTO") + 1])
    leitura = fixDate(list(filter(lambda x: x.find(
        "Comunicação de leituras") != -1, lines))[0].split(" ")[-1])
    return {'REFERÊNCIA': ref, 'ENTIDADE': ent, 'MONTANTE': mon, 'DATA LIMITE': date, 'PRÓXIMA LEITURA': leitura}


def extractEdp(path):
    lines = readPdf(path, -1)
    try:
        index = lines.index("Data limite de pagamento:") + 1
        ent = lines[index].strip()
        ref = lines[index + 1].strip()
        mon = lines[index + 2].strip()
        date = lines[index + 3].strip()
        date = "".join([c if c.isalnum() else "-" for c in date])
        leitura = '22-' + '-'.join(date.split('-')[1:])
        return {'REFERÊNCIA': ref, 'ENTIDADE': ent, 'MONTANTE': mon, 'DATA LIMITE': date, 'PRÓXIMA LEITURA': leitura}
    except:
        sys.exit("EDP FATURA ERRO! IMPRIMIR EM PDF")


def extractEventInfoFromFaturaInfo(company, info):
    title = 'Fatura ' + company
    description = ''
    for k in info:
        description += k + ": " + info[k] + "\n"
    start = parseTime(info['DATA LIMITE'])
    leitura = parseTime(info['PRÓXIMA LEITURA'])
    return {'title': title, 'description': description, 'start': start}


def extractEventInfoFromFaturaInfoLeitura(company, info):
    title = 'Leitura ' + company
    description = ''
    start = parseTime(info['PRÓXIMA LEITURA'])
    return {'title': title, 'description': description, 'start': start}


def main():
    edps = []
    epals = []
    golds = []
    files = [f for f in os.listdir('.') if os.path.isfile(
        f) and f.lower().find('.pdf') != -1]
    for f in files:
        if f.lower().find("edp") != -1:
            edps.append(extractEdp(f))
        elif f.lower().find("gold") != -1:
            golds.append(extractGold(f))
        elif f.lower().find("epal") != -1:
            epals.append(extractEpal(f))

    infos = []
    for e in edps:
        infos.append(extractEventInfoFromFaturaInfo("EDP", e))
        infos.append(extractEventInfoFromFaturaInfoLeitura("EDP", e))
    for e in epals:
        infos.append(extractEventInfoFromFaturaInfo("EPAL", e))
        infos.append(extractEventInfoFromFaturaInfoLeitura("EPAL", e))
    for e in golds:
        infos.append(extractEventInfoFromFaturaInfo("Gold", e))
        infos.append(extractEventInfoFromFaturaInfoLeitura("Gold", e))

    service = initializeGoogleApi()
    for i in infos:
        result = createEvent(service, i["title"], i["description"], i["start"])
        print("Created event for {} at {}".format(i["title"], result))

    todayDir = datetime.datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(todayDir):
        os.makedirs(todayDir)

    for f in files:
        os.rename(f, os.path.join(todayDir, f))


if __name__ == "__main__":
    main()
