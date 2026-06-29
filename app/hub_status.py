from __future__ import annotations

from app.domain_contracts import (
    JOB_STATUS_APPROVED_FOR_PUBLISH,
    JOB_STATUS_BLOCKED_FOR_MONETIZATION,
    JOB_STATUS_FAILED,
    JOB_STATUS_MONETIZATION_REVIEW,
    JOB_STATUS_PUBLISHED,
    JOB_STATUS_READY_FOR_UPLOAD,
    JOB_STATUS_REJECTED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SCHEDULED_PUBLICATION,
    JOB_STATUS_UNSCHEDULED_APPROVED,
    NEEDS_ACTION_JOB_STATUSES,
    PUBLICATION_STATUS_CANCELLED,
    PUBLICATION_STATUS_PUBLISH_FAILED,
    PUBLICATION_STATUS_PUBLISHED,
    PUBLICATION_STATUS_PUBLISHING,
    PUBLICATION_STATUS_SCHEDULED,
)

JOB_STATUS_LABELS = {
    "needs_action": "Ação pendente",
    "queued": "Na fila",
    JOB_STATUS_RUNNING: "Gerando vídeo",
    "script_quality_failed": "Falhou no roteiro",
    "visual_contract_quality_failed": "Falhou no contrato visual",
    "scene_plan_quality_failed": "Falhou nas cenas",
    "asset_quality_failed": "Falhou nos assets",
    "subtitle_quality_failed": "Falhou nas legendas",
    "render_quality_failed": "Falhou no render",
    JOB_STATUS_MONETIZATION_REVIEW: "Precisa revisão",
    JOB_STATUS_BLOCKED_FOR_MONETIZATION: "Bloqueado para publicar",
    JOB_STATUS_READY_FOR_UPLOAD: "Pronto para aprovar",
    JOB_STATUS_APPROVED_FOR_PUBLISH: "Aprovado para publicar",
    JOB_STATUS_UNSCHEDULED_APPROVED: "Aprovado sem agenda",
    JOB_STATUS_SCHEDULED_PUBLICATION: "Programado",
    "awaiting_confirmation": "Aguardando confirmação",
    "publication_failed": "Falha de publicação",
    JOB_STATUS_PUBLISHED: "Publicado",
    "approved": "Aprovado",
    JOB_STATUS_REJECTED: "Rejeitado",
    JOB_STATUS_FAILED: "Falhou",
}

SCHEDULE_STATUS_LABELS = {
    PUBLICATION_STATUS_SCHEDULED: "Programado",
    PUBLICATION_STATUS_PUBLISHING: "Publicando",
    PUBLICATION_STATUS_PUBLISH_FAILED: "Falhou no upload",
    PUBLICATION_STATUS_PUBLISHED: "Publicado",
    PUBLICATION_STATUS_CANCELLED: "Programação limpa",
}
