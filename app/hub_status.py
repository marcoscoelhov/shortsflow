from __future__ import annotations

JOB_STATUS_LABELS = {
    "needs_action": "Ação pendente",
    "queued": "Na fila",
    "running": "Gerando vídeo",
    "script_quality_failed": "Falhou no roteiro",
    "visual_contract_quality_failed": "Falhou no contrato visual",
    "scene_plan_quality_failed": "Falhou nas cenas",
    "asset_quality_failed": "Falhou nos assets",
    "subtitle_quality_failed": "Falhou nas legendas",
    "render_quality_failed": "Falhou no render",
    "monetization_review": "Precisa revisão",
    "blocked_for_monetization": "Bloqueado para publicar",
    "ready_for_upload": "Pronto para aprovar",
    "approved_for_publish": "Aprovado para publicar",
    "unscheduled_approved": "Aprovado sem agenda",
    "scheduled_publication": "Programado",
    "awaiting_confirmation": "Aguardando confirmação",
    "publication_failed": "Falha de publicação",
    "published": "Publicado",
    "approved": "Aprovado",
    "rejected": "Rejeitado",
    "failed": "Falhou",
}

SCHEDULE_STATUS_LABELS = {
    "scheduled": "Programado",
    "publishing": "Publicando",
    "publish_failed": "Falhou no upload",
    "published": "Publicado",
    "cancelled": "Programação limpa",
}

NEEDS_ACTION_JOB_STATUSES = {
    "monetization_review",
    "ready_for_upload",
    "blocked_for_monetization",
    "rejected",
    "failed",
}
