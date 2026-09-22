from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Legacy Credit Union Admin")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

MEMBERS = {
    "12345": {
        "name": "Alex Morgan",
        "status": "Active",
        "checking_balance": "1,420.18",
        "savings_balance": "4,830.42",
    },
    "56789": {
        "name": "Jordan Lee",
        "status": "Active",
        "checking_balance": "785.10",
        "savings_balance": "9,215.33",
    },
}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"page_title": "Member Search"},
    )


@app.post("/members/search", response_class=HTMLResponse)
def search_member(request: Request, member_id: str = Form(...)):
    member_id = member_id.strip()

    if member_id == "99999" or member_id not in MEMBERS:
        return templates.TemplateResponse(
            request=request,
            name="not_found.html",
            context={
                "page_title": "Member Search",
                "member_id": member_id,
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        request=request,
        name="member.html",
        context={
            "page_title": "Member Details",
            "member_id": member_id,
            "member": MEMBERS[member_id],
        },
    )


@app.get("/members/{member_id}", response_class=HTMLResponse)
def member_detail(request: Request, member_id: str):
    member = MEMBERS.get(member_id)

    if not member:
        return templates.TemplateResponse(
            request=request,
            name="not_found.html",
            context={
                "page_title": "Member Search",
                "member_id": member_id,
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        request=request,
        name="member.html",
        context={
            "page_title": "Member Details",
            "member_id": member_id,
            "member": member,
        },
    )


@app.get(
    "/members/{member_id}/subaccounts/new",
    response_class=HTMLResponse,
)
def new_subaccount(request: Request, member_id: str):
    member = MEMBERS.get(member_id)

    if not member:
        return templates.TemplateResponse(
            request=request,
            name="not_found.html",
            context={
                "page_title": "Member Search",
                "member_id": member_id,
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        request=request,
        name="open_subaccount.html",
        context={
            "page_title": "Open Sub-account",
            "member_id": member_id,
            "member": member,
        },
    )


@app.post(
    "/members/{member_id}/subaccounts/review",
    response_class=HTMLResponse,
)
def review_subaccount(
    request: Request,
    member_id: str,
    account_type: str = Form(...),
    nickname: str = Form(""),
):
    member = MEMBERS.get(member_id)

    if not member:
        return templates.TemplateResponse(
            request=request,
            name="not_found.html",
            context={
                "page_title": "Member Search",
                "member_id": member_id,
            },
            status_code=404,
        )

    account_type = account_type.strip().lower()
    if account_type not in {"checking", "savings"}:
        return templates.TemplateResponse(
            request=request,
            name="open_subaccount.html",
            context={
                "page_title": "Open Sub-account",
                "member_id": member_id,
                "member": member,
                "error": "Please select a valid account type.",
            },
            status_code=400,
        )

    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={
            "page_title": "Review New Sub-account",
            "member_id": member_id,
            "member": member,
            "account_type": account_type.title(),
            "nickname": nickname.strip() or "(none)",
        },
    )


@app.post(
    "/members/{member_id}/subaccounts/create",
    response_class=HTMLResponse,
)
def create_subaccount_demo(request: Request, member_id: str):
    member = MEMBERS.get(member_id)

    if not member:
        return templates.TemplateResponse(
            request=request,
            name="not_found.html",
            context={
                "page_title": "Member Search",
                "member_id": member_id,
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        request=request,
        name="created.html",
        context={
            "page_title": "Sub-account Created",
            "member_id": member_id,
            "member": member,
        },
    )
