from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from artifacts import ArtifactNotFoundError, get_artifact, list_artifacts
from llm import validate_llm_config
from router import chat_stream
from sessions import (
    clear_session,
    list_session_summaries,
    normalize_device_id,
    session_snapshot,
    set_artifact_context,
    set_image_context,
)
from vision import (
    CameraUploadError,
    build_manual_vision_result,
    build_unrecognized_vision_result,
    save_camera_image,
)
from vision_llm import (
    VisionConfigError,
    VisionRecognitionError,
    is_vision_configured,
    recognize_artifact_from_image,
)


app = FastAPI(title="Minimal AI Chat Backend")


class ChatRequest(BaseModel):
    message: str
    device: str = "default"


class ArtifactContextRequest(BaseModel):
    artifact_id: str
    vision_description: str | None = None
    image_id: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sessions")
async def sessions() -> list[dict[str, object]]:
    return list_session_summaries()


@app.get("/artifacts")
async def artifacts() -> list[dict[str, object]]:
    return list_artifacts()


@app.get("/artifacts/{artifact_id}")
async def artifact_detail(artifact_id: str) -> dict[str, object]:
    try:
        return get_artifact(artifact_id)
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc


@app.get("/sessions/{device_id}")
async def get_device_session(device_id: str) -> dict[str, object]:
    return session_snapshot(device_id)


@app.post("/sessions/{device_id}/clear")
async def clear_device_session(device_id: str) -> dict[str, str]:
    clear_session(device_id)
    return {"status": "cleared", "device_id": normalize_device_id(device_id)}


@app.post("/sessions/{device_id}/artifact-context")
async def set_device_artifact_context(
    device_id: str, request: ArtifactContextRequest
) -> dict[str, object]:
    artifact_id = request.artifact_id.strip()
    if not artifact_id:
        raise HTTPException(status_code=400, detail="artifact_id cannot be empty")

    try:
        artifact = get_artifact(artifact_id)
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc

    session = set_artifact_context(
        device_id=normalize_device_id(device_id),
        artifact_id=artifact_id,
        vision_description=request.vision_description,
        image_id=request.image_id,
    )
    return {
        "status": "ready",
        "device_id": session.device_id,
        "latest_artifact_id": session.latest_artifact_id,
        "latest_artifact_name": artifact["name"],
        "latest_image_id": session.latest_image_id,
        "latest_vision_description": session.latest_vision_description,
        "upload_generation": session.upload_generation,
    }


@app.post("/camera/upload")
async def upload_camera_image(
    request: Request,
    device: str = "default",
    artifact_id: str | None = None,
    vision_description: str | None = None,
    use_vision: bool = True,
) -> dict[str, object]:
    device_id = normalize_device_id(device)
    normalized_artifact_id = (artifact_id or "").strip()
    artifact = None
    if normalized_artifact_id:
        try:
            artifact = get_artifact(normalized_artifact_id)
        except ArtifactNotFoundError as exc:
            raise HTTPException(status_code=404, detail="artifact not found") from exc

    image_bytes = await request.body()
    try:
        saved_image = save_camera_image(
            device_id=device_id,
            image_bytes=image_bytes,
            content_type=request.headers.get("content-type"),
        )
    except CameraUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if artifact is not None:
        recognition = build_manual_vision_result(artifact, vision_description)
        session = set_artifact_context(
            device_id=device_id,
            artifact_id=normalized_artifact_id,
            vision_description=str(recognition["vision_description"]),
            image_id=str(saved_image["image_id"]),
        )
    elif use_vision and is_vision_configured():
        try:
            recognition = await recognize_artifact_from_image(
                image_bytes=image_bytes,
                content_type=str(saved_image["content_type"]),
            )
        except (VisionConfigError, VisionRecognitionError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        recognized_artifact_id = recognition.get("artifact_id")
        if recognized_artifact_id:
            session = set_artifact_context(
                device_id=device_id,
                artifact_id=str(recognized_artifact_id),
                vision_description=str(recognition.get("vision_description") or ""),
                image_id=str(saved_image["image_id"]),
            )
        else:
            session = set_image_context(
                device_id=device_id,
                image_id=str(saved_image["image_id"]),
                vision_description=recognition.get("vision_description"),
            )
    else:
        recognition = build_unrecognized_vision_result(vision_description)
        session = set_image_context(
            device_id=device_id,
            image_id=str(saved_image["image_id"]),
            vision_description=recognition["vision_description"],
        )

    return {
        "status": "ready",
        "device_id": session.device_id,
        "image": saved_image,
        "recognition": recognition,
        "latest_artifact_id": session.latest_artifact_id,
        "latest_image_id": session.latest_image_id,
        "latest_vision_description": session.latest_vision_description,
        "upload_generation": session.upload_generation,
    }


@app.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="message cannot be empty")

    try:
        validate_llm_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return StreamingResponse(
        chat_stream(user_message, normalize_device_id(request.device)),
        media_type="text/plain; charset=utf-8",
    )
