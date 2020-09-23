from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup
from pytz import timezone
from yarl import URL
from fastapi import Query, FastAPI
from icalendar import Event, Calendar
from fastapi.responses import Response

FIRST = datetime(2020, 9, 13, tzinfo=timezone("Asia/Shanghai"))  # 学期第一周的周日，即开学前一天
assert FIRST.weekday() == 6


def data_to_ics(data):

    cal = Calendar()
    cal.add("prodid", "-//ustc timetable//timetable//CN")
    cal.add("version", "2.0")
    cal.add("TZID", "Asia/Shanghai")
    cal.add("X-WR-TIMEZONE", "Asia/Shanghai")

    # MODE = "CN"
    # print(
    #     data["studentTableVm"]["name"],
    #     data["studentTableVm"]["code"],
    #     data["studentTableVm"]["department"],
    #     "本学期学分",
    #     data["studentTableVm"]["credits"],
    #     data["studentTableVm"]["major"],
    # )
    for c in data["studentTableVm"]["activities"]:
        summary = c["courseName"]
        location = " ".join(
            x for x in [c["campus"], c["customPlace"], c["building"], c["room"]] if x
        )
        description = "{} {} {}周 {}学分".format(
            location,
            " ".join(c["teachers"]),
            c["weeksStr"],
            c["credits"],
        )
        status = 0  # 0每周 1单周 2双周
        weeksStr = c["weeksStr"]
        if weeksStr.find("单") > -1:
            status = 1
            weeksStr = weeksStr.replace("单", "")
        elif weeksStr.find("双") > -1:
            status = 2
            weeksStr = weeksStr.replace("双", "")
        if "," in weeksStr:
            split_week_str = [x.strip() for x in weeksStr.split(",")]
        elif "-" not in weeksStr:
            split_week_str = [f"{weeksStr}-{weeksStr}"]
        else:
            split_week_str = [weeksStr]
        for weeks_str in split_week_str:
            weekday = int(c["weekday"])
            start_week, end_week = map(int, weeks_str.split("-"))
            start_hour, start_min = map(int, c["startDate"].split(":"))
            end_hour, end_min = map(int, c["endDate"].split(":"))
            event = Event()
            event.add("summary", summary)
            event.add("location", location)
            event.add("description", description)
            event.add(
                "dtstart",
                FIRST
                + timedelta(
                    days=weekday,
                    weeks=start_week - 1,
                    hours=start_hour,
                    minutes=start_min,
                ),
            )
            event.add(
                "dtend",
                FIRST
                + timedelta(
                    days=weekday, weeks=start_week - 1, hours=end_hour, minutes=end_min
                ),
            )
            event.add("dtstamp", datetime.utcnow())
            interval = 2 if status else 1
            event.add(
                "rrule",
                {
                    "freq": "weekly",
                    "interval": interval,
                    "count": (end_week - start_week) // interval + 1,
                },
            )
            cal.add_component(event)
    return cal.to_ical()


async def login(username, password):
    print("login...")
    service = "http://yjs.ustc.edu.cn/default.asp"
    url = URL.build(
        scheme="https",
        host="passport.ustc.edu.cn",
        path="/login",
        query={"service": service},
    )
    data = {
        "model": "uplogin.jsp",
        "service": service,
        "username": username,
        "password": password,
    }
    session = client
    await session.post(str(url), data=data)
    return session


client = httpx.AsyncClient()


async def get_calendar(username, password):
    session = await login(username, password)
    sidebar = await session.get("http://yjs.ustc.edu.cn/m_left.asp?area=5&menu=1")
    soup = BeautifulSoup(sidebar.text, "html.parser")
    session_id_name = None
    session_id_value = None
    for x in session.cookies.jar:
        if x.name.startswith("ASPSESSIONID"):
            session_id_name = x.name
            session_id_value = x.value
    if not (session_id_name and session_id_value):
        raise ValueError()
    href = soup.find("a", id="mm_2").attrs["href"]
    await session.get(
        str(
            URL(href).update_query(
                {session_id_name: session_id_value},
            )
        )
    )
    redirector_page = await session.get("https://jw.ustc.edu.cn/for-std/course-table")
    soup = BeautifulSoup(redirector_page.text, "html.parser")
    week_index = soup.select_one(
        "select#allSemesters > option[selected='selected']"
    ).attrs["value"]
    student_id = redirector_page.url.path.split("/")[-1]
    data = await session.get(
        f"https://jw.ustc.edu.cn/for-std/course-table/semester/{week_index}/print-data/{student_id}?weekIndex="
    )
    return data_to_ics(data.json())


app = FastAPI()


class CalendarResponse(Response):
    # media_type = "text/calendar"
    media_type = "text/plain"
    # pass


@app.get("/dispatch", response_class=CalendarResponse)
async def dispatch(username: str = Query(...), password: str = Query(...)):
    return await get_calendar(username, password)
