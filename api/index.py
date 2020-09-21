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
        location = " ".join([c["campus"] or c["customPlace"], c["room"] or ""])
        description = " ".join(
            x.strip()
            for x in [
                c["campus"] or c["customPlace"],
                c["building"] or "",
                " ".join(c["teachers"]).strip(),
                c["weeksStr"] + "周",
                c["lessonCode"],
                str(c["credits"]) + "学分",
            ]
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
            splited_week_str = [x.strip() for x in weeksStr.split(",")]
        elif "-" not in weeksStr:
            splited_week_str = [f"{weeksStr}-{weeksStr}"]
        else:
            splited_week_str = [weeksStr]
        for weeksStr in splited_week_str:
            startWeek = int(weeksStr.split("-")[0])
            endWeek = int(weeksStr.split("-")[1])
            weekday = int(c["weekday"])
            sHour = int(c["startDate"].split(":")[0])
            sMin = int(c["startDate"].split(":")[1])
            eHour = int(c["endDate"].split(":")[0])
            eMin = int(c["endDate"].split(":")[1])
            event = Event()
            event.add("summary", summary)
            event.add("location", location)
            event.add("description", description)
            event.add(
                "dtstart",
                FIRST
                + timedelta(
                    days=weekday, weeks=startWeek - 1, hours=sHour, minutes=sMin
                ),
            )
            event.add(
                "dtend",
                FIRST
                + timedelta(
                    days=weekday, weeks=startWeek - 1, hours=eHour, minutes=eMin
                ),
            )
            event.add("dtstamp", datetime.utcnow())
            interval = 2 if status else 1
            event.add(
                "rrule",
                {
                    "freq": "weekly",
                    "interval": interval,
                    "count": (endWeek - startWeek) // interval + 1,
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
    href = soup.find("a", id="mm_2").attrs["href"]
    session_id = session.cookies.get("ASPSESSIONIDQSTCCCTB", domain="yjs.ustc.edu.cn")
    await session.get(
        str(
            URL(href).update_query(
                {"ASPSESSIONIDQSTCCCTB": session_id},
            )
        )
    )
    data = await session.get(
        "https://jw.ustc.edu.cn/for-std/course-table/semester/181/print-data/149952?weekIndex="
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


if __name__ == "__main__":
    import asyncio

    print(asyncio.run(get_calendar()))
