"""Group (MUC) management endpoints."""

import logging
import os
import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from auth import verify_token
from models import (
    GroupAddMemberRequest,
    GroupCreateRequest,
    GroupCreateResponse,
    GroupInfo,
    GroupListResponse,
    GroupMember,
    GroupMembersResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/groups", tags=["groups"])

_EJABBERD_API_URL = os.environ.get("EJABBERD_API_URL", "https://ejabberd:5443/api")
_XMPP_DOMAIN = os.environ.get("XMPP_DOMAIN", "example.com")


@router.post("", status_code=status.HTTP_201_CREATED, response_model=GroupCreateResponse)
async def create_group(
    body: GroupCreateRequest,
    caller_jid: Annotated[str, Depends(verify_token)],
) -> GroupCreateResponse:
    """Create a new MUC room and set affiliations."""
    room_id = str(uuid.uuid4())
    muc_service = f"muc.{_XMPP_DOMAIN}"

    try:
        async with httpx.AsyncClient(verify=False) as client:
            # Create the room with options
            resp = await client.post(
                f"{_EJABBERD_API_URL}/create_room_with_opts",
                json={
                    "name": room_id,
                    "service": muc_service,
                    "host": _XMPP_DOMAIN,
                    "options": [
                        {"name": "title", "value": body.name},
                        {"name": "persistentroom", "value": "true"},
                        {"name": "membersonly", "value": "true"},
                        {"name": "allow_user_invites", "value": "true"},
                        {"name": "mam", "value": "true"},
                    ],
                },
                timeout=10.0,
            )
            if resp.status_code not in (200, 201):
                logger.error("create_room_with_opts returned %s: %s", resp.status_code, resp.text)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to create group room.",
                )

            # Set creator as owner
            resp = await client.post(
                f"{_EJABBERD_API_URL}/set_room_affiliation",
                json={
                    "name": room_id,
                    "service": muc_service,
                    "jid": caller_jid,
                    "affiliation": "owner",
                },
                timeout=10.0,
            )
            if resp.status_code != 200:
                logger.error("set_room_affiliation (owner) returned %s: %s", resp.status_code, resp.text)

            # Add initial members
            for member_jid in body.member_jids:
                resp = await client.post(
                    f"{_EJABBERD_API_URL}/set_room_affiliation",
                    json={
                        "name": room_id,
                        "service": muc_service,
                        "jid": member_jid,
                        "affiliation": "member",
                    },
                    timeout=10.0,
                )
                if resp.status_code != 200:
                    logger.error(
                        "set_room_affiliation (member %s) returned %s: %s",
                        member_jid, resp.status_code, resp.text,
                    )
    except httpx.HTTPError:
        logger.exception("Failed to reach Ejabberd admin API")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Group service unavailable. Please try again later.",
        )

    room_jid = f"{room_id}@{muc_service}"
    return GroupCreateResponse(group_id=room_id, jid=room_jid, name=body.name)


@router.get("", response_model=GroupListResponse)
async def list_groups(
    caller_jid: Annotated[str, Depends(verify_token)],
) -> GroupListResponse:
    """List MUC rooms the caller belongs to."""
    username = caller_jid.split("@")[0]
    muc_service = f"muc.{_XMPP_DOMAIN}"

    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                f"{_EJABBERD_API_URL}/get_user_rooms",
                json={"user": username, "host": _XMPP_DOMAIN},
                timeout=10.0,
            )
            if resp.status_code != 200:
                logger.error("get_user_rooms returned %s: %s", resp.status_code, resp.text)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to list groups.",
                )

            rooms = resp.json()
            groups: list[GroupInfo] = []
            for room_jid in rooms:
                room_name = room_jid.split("@")[0] if isinstance(room_jid, str) else room_jid
                # Get room title from options
                opts_resp = await client.post(
                    f"{_EJABBERD_API_URL}/get_room_options",
                    json={"name": room_name, "service": muc_service},
                    timeout=10.0,
                )
                title = room_name
                if opts_resp.status_code == 200:
                    for opt in opts_resp.json():
                        if opt.get("name") == "title" and opt.get("value"):
                            title = opt["value"]
                            break

                full_jid = room_jid if "@" in str(room_jid) else f"{room_jid}@{muc_service}"
                groups.append(GroupInfo(group_id=room_name, jid=full_jid, name=title))

    except httpx.HTTPError:
        logger.exception("Failed to reach Ejabberd admin API")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Group service unavailable. Please try again later.",
        )

    return GroupListResponse(groups=groups)


@router.get("/{group_id}/members", response_model=GroupMembersResponse)
async def list_members(
    group_id: str,
    caller_jid: Annotated[str, Depends(verify_token)],
) -> GroupMembersResponse:
    """List members of a MUC room."""
    muc_service = f"muc.{_XMPP_DOMAIN}"

    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                f"{_EJABBERD_API_URL}/get_room_affiliations",
                json={"name": group_id, "service": muc_service},
                timeout=10.0,
            )
    except httpx.HTTPError:
        logger.exception("Failed to reach Ejabberd admin API")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Group service unavailable. Please try again later.",
        )

    if resp.status_code != 200:
        logger.error("get_room_affiliations returned %s: %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to list group members.",
        )

    affiliations = resp.json()
    members = [
        GroupMember(
            jid=entry.get("username", ""),
            affiliation=entry.get("domain", ""),
        )
        if "username" in entry
        else GroupMember(
            jid=entry.get("jid", ""),
            affiliation=entry.get("affiliation", ""),
        )
        for entry in affiliations
    ]
    return GroupMembersResponse(members=members)


@router.post("/{group_id}/members", status_code=status.HTTP_200_OK)
async def add_member(
    group_id: str,
    body: GroupAddMemberRequest,
    caller_jid: Annotated[str, Depends(verify_token)],
) -> dict:
    """Add a member to a MUC room."""
    muc_service = f"muc.{_XMPP_DOMAIN}"

    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                f"{_EJABBERD_API_URL}/set_room_affiliation",
                json={
                    "name": group_id,
                    "service": muc_service,
                    "jid": body.jid,
                    "affiliation": "member",
                },
                timeout=10.0,
            )
    except httpx.HTTPError:
        logger.exception("Failed to reach Ejabberd admin API")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Group service unavailable. Please try again later.",
        )

    if resp.status_code != 200:
        logger.error("set_room_affiliation returned %s: %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to add member.",
        )

    return {"status": "ok"}


@router.delete("/{group_id}/members/{jid}", status_code=status.HTTP_200_OK)
async def remove_member(
    group_id: str,
    jid: str,
    caller_jid: Annotated[str, Depends(verify_token)],
) -> dict:
    """Remove a member from a MUC room."""
    muc_service = f"muc.{_XMPP_DOMAIN}"

    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                f"{_EJABBERD_API_URL}/set_room_affiliation",
                json={
                    "name": group_id,
                    "service": muc_service,
                    "jid": jid,
                    "affiliation": "none",
                },
                timeout=10.0,
            )
    except httpx.HTTPError:
        logger.exception("Failed to reach Ejabberd admin API")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Group service unavailable. Please try again later.",
        )

    if resp.status_code != 200:
        logger.error("set_room_affiliation returned %s: %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to remove member.",
        )

    return {"status": "ok"}
