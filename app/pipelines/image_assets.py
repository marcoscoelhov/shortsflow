from __future__ import annotations

import queue
import re
import threading
from pathlib import Path
from typing import Any

from PIL import Image

from app.pipelines.common import RecoverableStepError
from app.utils import path_from_uri


MINIMAX_IMAGE_PROMPT_MAX_CHARS = 1500
MINIMAX_IMAGE_PROMPT_TARGET_CHARS = 1200

NO_TEXT_IMAGE_CONSTRAINT = (
    "clean vertical cinematic image, no readable text anywhere, no letters, no words, "
    "no numbers, no symbols, no logo, no watermark, no captions, no subtitles, "
    "no typography, no labels, no UI, no signs, no text printed on objects"
)

SINGLE_VERTICAL_IMAGE_CONSTRAINT = (
    "single full-frame 9:16 vertical image, no split screen, no side-by-side, no collage, "
    "no panels, no picture-in-picture, no timeline, no arrows, no guide lines, no overlay graphics"
)

ENGLISH_SUBJECT_ALIASES = {
    "polvo": "octopus",
    "polvos": "octopuses",
    "buraco negro": "black hole",
    "buracos negros": "black holes",
    "vulcao": "volcano",
    "vulcoes": "volcanoes",
    "vulcão": "volcano",
    "vulcões": "volcanoes",
    "gato": "cat",
    "gatos": "cats",
    "felino": "cat",
    "felinos": "cats",
    "cafe": "coffee",
    "café": "coffee",
    "cafeina": "caffeine",
    "cafeína": "caffeine",
    "cafeina e foco": "caffeine and focus",
    "café e foco": "coffee and focus",
    "torre de pisa": "Leaning Tower of Pisa",
    "torre inclinada de pisa": "Leaning Tower of Pisa",
    "por que a torre de pisa não cai?": "Leaning Tower of Pisa",
    "por que a torre de pisa nao cai?": "Leaning Tower of Pisa",
    "diorama de cidade abandonada": "abandoned miniature city diorama",
    "maquete de cidade": "miniature city diorama",
    "maquete urbana": "miniature urban diorama",
    "cidade em miniatura": "miniature city",
    "cidade falsa": "miniature city illusion",
}

SCENE_VISUAL_HINTS = [
    (("torre", "pisa", "séculos"), "the Leaning Tower of Pisa in Piazza dei Miracoli at golden hour, visibly tilted but stable, documentary realism"),
    (("torre", "pisa", "seculos"), "the Leaning Tower of Pisa in Piazza dei Miracoli at golden hour, visibly tilted but stable, documentary realism"),
    (("solo", "argiloso"), "cutaway view of the Leaning Tower of Pisa foundation resting on soft clay soil layers, unlabeled scientific visualization"),
    (("solo", "mole"), "cutaway view of the Leaning Tower of Pisa foundation resting on soft clay soil layers, unlabeled scientific visualization"),
    (("fundação",), "close vertical cutaway of a shallow medieval tower foundation settling into soft ground, documentary engineering realism"),
    (("fundacao",), "close vertical cutaway of a shallow medieval tower foundation settling into soft ground, documentary engineering realism"),
    (("centro", "massa"), "unlabeled visual metaphor of the Leaning Tower of Pisa balancing with its mass still over the base, no diagrams or text"),
    (("inclinação", "reduz"), "engineers stabilizing the base of the Leaning Tower of Pisa with careful soil extraction, documentary realism"),
    (("inclinacao", "reduz"), "engineers stabilizing the base of the Leaning Tower of Pisa with careful soil extraction, documentary realism"),
    (("cafeina", "foco"), "caffeine molecules near alert neurons in warm morning light, a plain unbranded coffee cup nearby"),
    (("cafeína", "foco"), "caffeine molecules near alert neurons in warm morning light, a plain unbranded coffee cup nearby"),
    (("cafe", "foco"), "plain unbranded coffee cup beside a focused morning workspace, subtle neural energy glow"),
    (("café", "foco"), "plain unbranded coffee cup beside a focused morning workspace, subtle neural energy glow"),
    (("adenosina",), "caffeine molecules blocking adenosine receptors on neurons, cinematic scientific visualization"),
    (("receptores",), "caffeine molecules fitting into neural receptors, cinematic scientific visualization"),
    (("sonolencia",), "sleep pressure fading from a human silhouette after caffeine reaches the brain, morning light"),
    (("sonolência",), "sleep pressure fading from a human silhouette after caffeine reaches the brain, morning light"),
    (("alerta",), "alert brain activity represented by glowing neural pathways beside plain coffee steam"),
    (("manhã",), "soft morning kitchen light with plain unbranded coffee steam and a person becoming alert in silhouette"),
    (("manha",), "soft morning kitchen light with plain unbranded coffee steam and a person becoming alert in silhouette"),
    (("gatos", "veem", "mundo diferente"), "cat face close-up with reflective eyes perceiving an altered night world"),
    (("terceiro", "párpado"), "macro close-up of a cat eye showing the translucent third eyelid protecting the eye"),
    (("terceiro", "parpado"), "macro close-up of a cat eye showing the translucent third eyelid protecting the eye"),
    (("orelha", "180"), "cat ears rotating independently toward subtle sound waves in a quiet room"),
    (("visão noturna",), "cat moving through a dim night scene with bright reflective eyes and low light visibility"),
    (("visao noturna",), "cat moving through a dim night scene with bright reflective eyes and low light visibility"),
    (("memória episódica",), "cat remembering a hidden toy location in a realistic home environment"),
    (("memoria episodica",), "cat remembering a hidden toy location in a realistic home environment"),
    (("cabeça", "180"), "cat turning its head sharply to monitor a distant threat, natural posture"),
    (("cabeca", "180"), "cat turning its head sharply to monitor a distant threat, natural posture"),
    (("corações", "sangue azul"), "octopus anatomy close-up showing three subtle hearts and blue copper-rich blood vessels"),
    (("coracoes", "sangue azul"), "octopus anatomy close-up showing three subtle hearts and blue copper-rich blood vessels"),
    (("hemocianina",), "blue oxygen-carrying blood flowing through octopus anatomy"),
    (("dna",), "octopus adapting underwater beside clean molecular DNA strands made of light"),
    (("células nervosas",), "octopus arms exploring rocks independently with subtle neural glow inside the tentacles"),
    (("celulas nervosas",), "octopus arms exploring rocks independently with subtle neural glow inside the tentacles"),
    (("tentáculo", "cortado"), "detached octopus arm moving reflexively on the seabed, natural biology, non-graphic"),
    (("tentaculo", "cortado"), "detached octopus arm moving reflexively on the seabed, natural biology, non-graphic"),
    (("cor", "textura", "predadores"), "octopus rapidly changing skin color and texture while camouflaging from a predator"),
    (("cidade", "palma"), "hyper realistic miniature city block resting in an open palm, tiny streets, cars, trees and apartment buildings clearly visible"),
    (("cidade", "inteira"), "hyper realistic miniature city block with tiny streets, cars, trees and apartment buildings, convincing real-city scale illusion"),
    (("maquete", "mesa"), "top-down miniature urban diorama on a craft table, tiny streets and buildings lit like a real aerial photo"),
    (("detalhes", "minuciosos"), "macro view of an outdoor miniature city street model, tiny painted building facades, toy cars, street lamps and asphalt road markings"),
    (("detalhes", "minucioso"), "macro view of an outdoor miniature city street model, tiny painted building facades, toy cars, street lamps and asphalt road markings"),
    (("detalhes", "dioramas"), "macro view of an outdoor miniature city street model, tiny painted building facades, toy cars, street lamps and asphalt road markings"),
    (("obturador", "borrão"), "close-up of a toy car on a miniature asphalt road with motion blur streaks, camera shutter implied by lens reflection, outdoor city diorama"),
    (("obturador", "borrao"), "close-up of a toy car on a miniature asphalt road with motion blur streaks, camera shutter implied by lens reflection, outdoor city diorama"),
    (("carrinhos", "movimento"), "close-up of a toy car on a miniature asphalt road with motion blur streaks, outdoor city diorama"),
    (("computação", "gráfica"), "miniature city street practical-effects comparison, same toy car shown sharp and with a motion blur trail on an outdoor model road"),
    (("computacao", "grafica"), "miniature city street practical-effects comparison, same toy car shown sharp and with a motion blur trail on an outdoor model road"),
    (("led", "fumaca"), "macro view of a miniature city building facade with warm LED window lights and subtle artificial smoke from a tiny chimney"),
    (("led", "fumaça"), "macro view of a miniature city building facade with warm LED window lights and subtle artificial smoke from a tiny chimney"),
    (("camera", "lente"), "side view of a camera lens aimed at a miniature city diorama, lens-distance perspective trick clearly visible"),
    (("câmera", "lente"), "side view of a camera lens aimed at a miniature city diorama, lens-distance perspective trick clearly visible"),
    (("lente", "distancia"), "side view of a camera lens aimed at a miniature city diorama, lens-distance perspective trick clearly visible"),
    (("lente", "distância"), "side view of a camera lens aimed at a miniature city diorama, lens-distance perspective trick clearly visible"),
    (("filmes", "games"), "miniature city diorama used as a practical-effects test, two tiny cars on the same model street, one blurred and one sharp"),
    (("filmes", "jogos"), "miniature city diorama used as a practical-effects test, two tiny cars on the same model street, one blurred and one sharp"),
    (("games", "borrao"), "miniature city diorama used as a practical-effects test, two tiny cars on the same model street, one blurred and one sharp"),
    (("jogos", "borrao"), "miniature city diorama used as a practical-effects test, two tiny cars on the same model street, one blurred and one sharp"),
]


class ImageAssetDomain:
    def __init__(self, pipeline: Any) -> None:
        self.pipeline = pipeline
        self.minimax_image_aspect_ratio = str(getattr(pipeline.settings, "minimax_image_aspect_ratio", "9:16"))

    def generate_primary_asset(self, job_id: str, scene: dict[str, Any], output_path: Path) -> dict[str, Any]:
        result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
        scene_for_provider = {**scene, "job_id": job_id}

        def run() -> None:
            try:
                result_queue.put(("ok", self.pipeline.providers.image.generate(scene_for_provider, output_path)), block=False)
            except BaseException as exc:  # noqa: BLE001
                result_queue.put(("error", exc), block=False)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(timeout=self.pipeline.settings.asset_generation_timeout_sec)
        if thread.is_alive():
            raise RecoverableStepError(
                f"asset primary generation timed out after {self.pipeline.settings.asset_generation_timeout_sec}s"
            )
        status, payload = result_queue.get_nowait()
        if status == "error":
            raise payload
        return payload

    def normalize_asset_uri_extension(self, asset: dict[str, Any]) -> dict[str, Any]:
        uri = str(asset.get("uri") or "")
        if not uri.startswith("file://"):
            return asset
        path = path_from_uri(uri)
        if not path.exists():
            return asset
        try:
            with Image.open(path) as image:
                fmt = (image.format or "").upper()
        except Exception:  # noqa: BLE001
            return asset
        suffix_by_format = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
        expected_suffix = suffix_by_format.get(fmt)
        if not expected_suffix or path.suffix.lower() == expected_suffix:
            return asset
        target = path.with_suffix(expected_suffix)
        counter = 2
        while target.exists() and target.resolve() != path.resolve():
            target = path.with_name(f"{path.stem}-{counter}{expected_suffix}")
            counter += 1
        path.rename(target)
        updated = dict(asset)
        updated["uri"] = target.resolve().as_uri()
        updated["file_format"] = fmt.lower()
        updated["extension_normalized"] = True
        return updated

    def score_asset(self, scene: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
        return self.pipeline.providers.semantic.score(scene, asset)

    def asset_scores_pass(self, scores: dict[str, Any]) -> bool:
        return (
            scores["semantic_match"] >= self.pipeline.settings.asset_semantic_threshold
            and scores["total_score"] >= self.pipeline.settings.asset_total_threshold
            and scores.get("text_or_watermark_penalty", 0.0) <= 0.15
            and scores.get("artifact_penalty", 0.0) <= 0.30
        )

    def image_prompt_variants(self, scene: dict[str, Any], regeneration_round: int = 1) -> list[dict[str, Any]]:
        topic_text = str(scene.get("topic_hint") or scene.get("primary_subject") or "")
        primary_subject = str(scene.get("primary_subject") or scene.get("topic_hint") or "")
        base_prompt = self.semantic_english_image_prompt(scene, topic_text, primary_subject)
        english_subject = self.english_subject_hint(topic_text, primary_subject)
        scene_hint = self.remove_incompatible_scientific_style(self.english_scene_visual_hint(scene, english_subject), scene)
        domain_style = self.visual_domain_style(scene)
        if self.is_visual_hook_scene(scene):
            variant_prompts = [
                base_prompt,
                self.with_no_text_image_constraints(
                    f"high-impact vertical first-frame hook for YouTube Shorts, {scene_hint}, "
                    "instant visual contrast, one unmistakable central subject, close composition, strong depth, "
                    f"concrete visual consequence visible immediately, {domain_style}, no later-payoff reveal"
                ),
                self.with_no_text_image_constraints(
                    f"stop-the-scroll {domain_style} frame, {english_subject} as the unmistakable central subject, "
                    f"{scene_hint}, visible tension or paradox in the first glance, natural dramatic lighting, "
                    "no calm establishing shot, no abstract ambience, no irrelevant props"
                ),
            ]
        else:
            variant_prompts = [
                base_prompt,
                self.with_no_text_image_constraints(
                    f"vertical documentary close shot of {english_subject}, {scene_hint}, "
                    f"visually illustrate this exact narration beat with {domain_style}, "
                    "natural lighting, one clear subject, no symbolic poster, no irrelevant props"
                ),
                self.with_no_text_image_constraints(
                    f"realistic vertical YouTube Shorts visual, {english_subject} as the unmistakable central subject, "
                    f"{scene_hint}, {domain_style}, concrete visual detail, clean relevant background"
                ),
            ]
        variants: list[dict[str, Any]] = []
        seen: set[str] = set()
        for prompt in variant_prompts:
            normalized = " ".join(prompt.split())
            if regeneration_round > 1:
                normalized = (
                    f"{normalized}, alternate composition, new camera framing, different background geometry, "
                    "keep the same factual subject and no text constraints"
                )
            if normalized.lower() in seen:
                continue
            seen.add(normalized.lower())
            variants.append({**scene, "image_prompt": self.minimax_safe_image_prompt(normalized, scene), "regeneration_round": regeneration_round})
        return variants

    def semantic_english_image_prompt(self, scene: dict[str, Any], topic_text: str, primary_subject: str) -> str:
        prompt = str(scene.get("image_prompt", "")).replace("_", " ")
        english_subject = self.english_subject_hint(topic_text, primary_subject)
        scene_hint = self.remove_incompatible_scientific_style(self.english_scene_visual_hint(scene, english_subject), scene)
        semantic_directive = self.semantic_scene_directive(scene, scene_hint)
        domain_style = self.visual_domain_style(scene)
        if self.should_rebuild_image_prompt(prompt) or self.prompt_conflicts_with_visual_domain(prompt, scene):
            visual_intent = str(scene.get("visual_intent") or "documentary scene").replace("_", " ")
            prompt = scene_hint or f"vertical cinematic {domain_style} of {english_subject}, {visual_intent}"
        else:
            prompt = self.replace_subject_aliases(prompt)
        prompt = self.remove_incompatible_scientific_style(prompt, scene)
        if semantic_directive.lower() not in prompt.lower():
            prompt = f"{prompt}, {semantic_directive}".strip(", ")
        conservative_science_directive = self.conservative_science_visual_directive(scene)
        if conservative_science_directive and conservative_science_directive.lower() not in prompt.lower():
            prompt = f"{prompt}, {conservative_science_directive}".strip(", ")
        if self.is_visual_hook_scene(scene):
            hook_directive = self.visual_hook_directive(scene, scene_hint)
            if hook_directive.lower() not in prompt.lower():
                prompt = f"{prompt}, {hook_directive}".strip(", ")
        if scene_hint and scene_hint.lower() not in prompt.lower():
            prompt = f"{scene_hint}, {prompt}".strip(", ")
        elif english_subject and english_subject.lower() not in prompt.lower():
            prompt = f"{prompt}, central subject: {english_subject}".strip(", ")
        style_directive = self.domain_style_directive(scene)
        if style_directive.lower() not in prompt.lower():
            prompt = f"{prompt}, {style_directive}".strip(", ")
        if "no movie poster" not in prompt.lower():
            prompt += ", no movie poster, no typography, no stock-photo generic scene"
        return self.minimax_safe_image_prompt(self.with_no_text_image_constraints(prompt), scene)

    def conservative_science_visual_directive(self, scene: dict[str, Any]) -> str:
        source_text = " ".join(
            str(scene.get(key) or "")
            for key in ("narration_text", "primary_subject", "image_prompt", "topic_hint", "visual_intent")
        ).lower()
        science_terms = {
            "anatomia",
            "fisiologia",
            "coração",
            "coracao",
            "corações",
            "coracoes",
            "brânquia",
            "branquia",
            "brânquias",
            "branquias",
            "sangue",
            "oxigênio",
            "oxigenio",
            "hemocianina",
            "systemic heart",
            "branchial hearts",
            "gills",
            "blood",
            "oxygen",
        }
        if not any(term in source_text for term in science_terms):
            return ""
        return (
            "conservative science visual, prefer external documentary evidence or a simple unlabeled cutaway, "
            "avoid invented organs, fantasy anatomy, glowing tubes, exaggerated transparent body, and unsupported medical-diagram detail"
        )

    def is_visual_hook_scene(self, scene: dict[str, Any]) -> bool:
        if str(scene.get("retention_role") or "").strip().lower() == "visual_hook":
            return True
        try:
            return int(scene.get("order", 0) or 0) == 1
        except (TypeError, ValueError):
            return False

    def english_subject_hint(self, topic_text: str, primary_subject: str) -> str:
        for value in [primary_subject, topic_text]:
            normalized = " ".join(str(value).replace("_", " ").lower().split())
            if normalized in ENGLISH_SUBJECT_ALIASES:
                return ENGLISH_SUBJECT_ALIASES[normalized]
            normalized_ascii = (
                normalized.replace("á", "a")
                .replace("à", "a")
                .replace("ã", "a")
                .replace("â", "a")
                .replace("é", "e")
                .replace("ê", "e")
                .replace("í", "i")
                .replace("ó", "o")
                .replace("õ", "o")
                .replace("ô", "o")
                .replace("ú", "u")
                .replace("ç", "c")
            )
            if "polvo" in normalized_ascii:
                return "octopus"
            if "gato" in normalized_ascii or "felino" in normalized_ascii:
                return "cat"
            if "buraco" in normalized_ascii and "negro" in normalized_ascii:
                return "black hole"
            if "vulcao" in normalized_ascii:
                return "volcano"
            if "cafeina" in normalized_ascii and "foco" in normalized_ascii:
                return "caffeine and focus"
            if "cafe" in normalized_ascii and "foco" in normalized_ascii:
                return "coffee and focus"
            if "cafeina" in normalized_ascii:
                return "caffeine"
            if "cafe" in normalized_ascii:
                return "coffee"
            if ("diorama" in normalized_ascii or "maquete" in normalized_ascii or "miniatura" in normalized_ascii) and (
                "cidade" in normalized_ascii or "urbana" in normalized_ascii or "urbano" in normalized_ascii
            ):
                return "miniature urban diorama"
            if "cidade" in normalized_ascii and ("falsa" in normalized_ascii or "miniatura" in normalized_ascii):
                return "miniature city illusion"
            if "cidade" in normalized_ascii:
                return "city"
        return primary_subject or topic_text or "the subject"

    def english_scene_visual_hint(self, scene: dict[str, Any], english_subject: str) -> str:
        narration = str(scene.get("narration_text") or "").lower()
        normalized = (
            narration.replace("á", "a")
            .replace("à", "a")
            .replace("ã", "a")
            .replace("â", "a")
            .replace("é", "e")
            .replace("ê", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("õ", "o")
            .replace("ô", "o")
            .replace("ú", "u")
            .replace("ç", "c")
        )
        for terms, hint in SCENE_VISUAL_HINTS:
            if all(term in narration or term in normalized for term in terms):
                return hint
        domain_style = self.visual_domain_style(scene)
        return f"vertical cinematic {domain_style} of {english_subject}"

    def semantic_scene_directive(self, scene: dict[str, Any], scene_hint: str) -> str:
        narration = str(scene.get("narration_text") or "").strip()
        visual_intent = str(scene.get("visual_intent") or "documentary evidence").replace("_", " ")
        if narration:
            return (
                "show this exact narration beat as concrete visual evidence, "
                f"not a generic symbolic background, focus: {scene_hint}, role: {visual_intent}"
            )
        return "show this exact narration beat as concrete visual evidence, not a generic symbolic background"

    def visual_domain_style(self, scene: dict[str, Any]) -> str:
        domain = self.normalized_visual_domain(scene)
        if self.is_science_visual_domain(scene):
            return "scientific documentary realism"
        if any(term in domain for term in ("miniature", "diorama", "maquete", "model", "craft", "artesanal")):
            return "miniature craft documentary realism"
        if any(term in domain for term in ("urban", "urbano", "cidade", "city", "street", "rua")):
            return "urban documentary realism"
        if any(term in domain for term in ("historical", "histórico", "historico", "cultural", "culture")):
            return "cultural documentary realism"
        if "documentary realism" in domain:
            return "documentary realism"
        return "documentary realism"

    def domain_style_directive(self, scene: dict[str, Any]) -> str:
        style = self.visual_domain_style(scene)
        if self.is_science_visual_domain(scene):
            return f"{style}, scientific visualization only where the narration requires it"
        return f"{style}, domain-compatible objects only, no lab-diagram styling unless required"

    def remove_incompatible_scientific_style(self, prompt: str, scene: dict[str, Any]) -> str:
        if self.is_science_visual_domain(scene):
            return prompt
        style = self.visual_domain_style(scene)
        updated = prompt
        replacements = {
            "vertical cinematic scientific image": f"vertical cinematic {style}",
            "clean vertical cinematic scientific image": f"clean vertical cinematic {style}",
            "scientific visualization": style,
            "scientific documentary realism": style,
            "scientific documentary": style,
            "science documentary frame": style,
            "cinematic science documentary frame": style,
            "scientific image": style,
            "natural/scientific objects": "domain-relevant objects",
        }
        for source, target in replacements.items():
            updated = re.sub(re.escape(source), target, updated, flags=re.IGNORECASE)
        return " ".join(updated.split())

    def normalized_visual_domain(self, scene: dict[str, Any]) -> str:
        return " ".join(str(scene.get("visual_domain") or "").replace("_", " ").lower().split())

    def is_science_visual_domain(self, scene: dict[str, Any]) -> bool:
        domain = self.normalized_visual_domain(scene)
        if any(term in domain for term in ("science", "scientific", "biology", "biologia", "physics", "fisica", "física", "medical", "anatomy", "anatomia")):
            return True
        source_text = " ".join(
            str(scene.get(key) or "")
            for key in ("narration_text", "primary_subject", "image_prompt", "topic_hint", "visual_intent")
        ).lower()
        science_terms = {"anatomia", "sangue", "hemocianina", "receptores", "adenosina", "neuron", "caffeine", "blood", "oxygen"}
        return any(term in source_text for term in science_terms)

    def visual_hook_directive(self, scene: dict[str, Any], scene_hint: str) -> str:
        return (
            "first-frame hook for Shorts under one second, concrete contrast or consequence, "
            "do not reveal later payoff, close vertical composition, no calm establishing shot, "
            f"focus: {scene_hint}"
        )

    def should_rebuild_image_prompt(self, prompt: str) -> bool:
        prompt_lower = prompt.lower()
        return any(
            phrase in prompt_lower
            for phrase in [
                "ilustracao",
                "mostrando",
                "foco no fenomeno",
                "sem texto",
                "sem watermark",
                "sem capa",
                "sem tipografia",
                "focused on the described phenomenon",
                "showing subject closeup",
                "showing subject in context",
                "showing process or mechanism",
                "showing comparison",
                "showing scale reference",
                "showing historical evocation",
            ]
        )

    def prompt_conflicts_with_visual_domain(self, prompt: str, scene: dict[str, Any]) -> bool:
        if not self.is_miniature_diorama_domain(scene):
            return False
        prompt_lower = prompt.lower()
        forbidden_terms = {
            "video game character",
            "game character",
            "human character",
            "full-size person",
            "full size person",
            "man holding",
            "person holding",
            "gun",
            "weapon",
            "pistol",
            "rifle",
            "sunglasses",
            "game graphics",
            "screen interface",
            "ui screen",
            "poster",
            "posters",
            "billboard",
            "billboards",
            "street sign",
            "signage",
            "hand enters",
            "hand holding",
            "picking up",
            "plastic block",
            "revealing true size",
        }
        return any(term in prompt_lower for term in forbidden_terms)

    def replace_subject_aliases(self, prompt: str) -> str:
        updated = prompt
        for source, target in sorted(ENGLISH_SUBJECT_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
            updated = re.sub(rf"\b{re.escape(source)}\b", target, updated, flags=re.IGNORECASE)
        return updated

    def with_no_text_image_constraints(self, prompt: str) -> str:
        prompt = " ".join(prompt.replace("_", " ").split())
        prompt_lower = prompt.lower()
        extra_constraints = [
            "main subject unmistakable and relevant to the narration beat",
            "every visible object blank and unbranded",
            "no text on cups, packages, screens, charts or labels",
            SINGLE_VERTICAL_IMAGE_CONSTRAINT,
            "avoid random props, generic sci-fi objects and irrelevant backgrounds",
        ]
        if "no readable text anywhere" not in prompt_lower:
            prompt = f"{prompt}, {NO_TEXT_IMAGE_CONSTRAINT}".strip(", ")
            prompt_lower = prompt.lower()
        for constraint in extra_constraints:
            if constraint.lower() not in prompt_lower:
                prompt = f"{prompt}, {constraint}"
                prompt_lower = prompt.lower()
        return prompt

    def domain_negative_constraints(self, scene: dict[str, Any]) -> str:
        corpus = " ".join(
            str(scene.get(key) or "")
            for key in ("visual_domain", "primary_subject", "topic_hint", "narration_text", "image_prompt", "visual_intent")
        ).lower()
        corpus = (
            corpus.replace("á", "a")
            .replace("à", "a")
            .replace("ã", "a")
            .replace("â", "a")
            .replace("é", "e")
            .replace("ê", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("õ", "o")
            .replace("ô", "o")
            .replace("ú", "u")
            .replace("ç", "c")
        )
        if self.is_miniature_diorama_domain(scene, corpus=corpus):
            return (
                "plain outdoor miniature city diorama only: tiny asphalt streets, toy cars, blank model buildings, "
                "street lamps, road markings, camera lens perspective; no cups, containers, food, hands, people, "
                "weapons, screens, posters, storefronts, signs, numbers, letters or labels"
            )
        if self.is_science_visual_domain(scene):
            return "no labeled diagrams, no invented anatomy, no fantasy organs, no unsupported medical detail"
        return "no irrelevant props, no product packaging, no signage"

    def is_miniature_diorama_domain(self, scene: dict[str, Any], corpus: str | None = None) -> bool:
        if corpus is None:
            corpus = " ".join(
                str(scene.get(key) or "")
                for key in ("visual_domain", "primary_subject", "topic_hint", "narration_text", "image_prompt", "visual_intent")
            ).lower()
            corpus = (
                corpus.replace("á", "a")
                .replace("à", "a")
                .replace("ã", "a")
                .replace("â", "a")
                .replace("é", "e")
                .replace("ê", "e")
                .replace("í", "i")
                .replace("ó", "o")
                .replace("õ", "o")
                .replace("ô", "o")
                .replace("ú", "u")
                .replace("ç", "c")
            )
        return any(term in corpus for term in ("miniature", "diorama", "maquete", "model city", "cidade falsa", "cidade em miniatura"))

    def minimax_no_text_constraint(self, scene: dict[str, Any]) -> str:
        if self.is_miniature_diorama_domain(scene):
            return "no readable text, letters, numbers, logos, watermarks, signs, labels or UI"
        return NO_TEXT_IMAGE_CONSTRAINT

    def minimax_safe_image_prompt(self, prompt: str, scene: dict[str, Any]) -> str:
        prompt = " ".join(str(prompt or "").replace("_", " ").split())
        prompt = prompt.replace("Visual contract hook requirements:", "Required visual elements:")
        prompt = self.replace_subject_aliases(prompt)
        prompt = self.remove_incompatible_scientific_style(prompt, scene)
        if self.is_miniature_diorama_domain(scene):
            prompt = prompt.replace(NO_TEXT_IMAGE_CONSTRAINT, self.minimax_no_text_constraint(scene))

        required_constraints = [
            f"vertical {self.minimax_image_aspect_ratio} frame for YouTube Shorts",
            SINGLE_VERTICAL_IMAGE_CONSTRAINT,
            self.domain_negative_constraints(scene),
            self.minimax_no_text_constraint(scene),
        ]
        for constraint in required_constraints:
            if constraint.lower() not in prompt.lower():
                prompt = f"{prompt}, {constraint}".strip(", ")

        prompt = self._dedupe_prompt_clauses(prompt)
        if len(prompt) <= MINIMAX_IMAGE_PROMPT_TARGET_CHARS:
            return prompt

        clauses = [clause.strip() for clause in prompt.split(",") if clause.strip()]
        required_tail = self._dedupe_prompt_clauses(", ".join(required_constraints))
        head_budget = max(180, MINIMAX_IMAGE_PROMPT_TARGET_CHARS - len(required_tail) - 2)
        keep: list[str] = []
        for clause in clauses:
            if clause.lower() in required_tail.lower():
                continue
            if len(clause) > 260:
                clause = clause[:260].rsplit(" ", 1)[0].strip()
            candidate = ", ".join([*keep, clause])
            if len(candidate) <= head_budget:
                keep.append(clause)
        compact = self._dedupe_prompt_clauses(", ".join([*keep, required_tail]))
        if len(compact) > MINIMAX_IMAGE_PROMPT_TARGET_CHARS:
            compact = self._dedupe_prompt_clauses(required_tail)
        return compact.strip(" ,")

    def _dedupe_prompt_clauses(self, prompt: str) -> str:
        clauses = [clause.strip() for clause in re.split(r",|;", prompt) if clause.strip()]
        seen: set[str] = set()
        deduped: list[str] = []
        for clause in clauses:
            key = clause.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(clause)
        return ", ".join(deduped)
