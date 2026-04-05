from dataclasses import dataclass, field
import asyncio
import base64
import hashlib
import importlib
import importlib.util
import json
import mimetypes
import os
import uuid
from pathlib import Path
from types import ModuleType

duckdb: ModuleType | None
if importlib.util.find_spec("duckdb"):
    duckdb = importlib.import_module("duckdb")
else:
    duckdb = None

import flet as ft
from flet.auth.providers import GoogleOAuthProvider

# Limites para anexos (20MB total, 5MB para imagens inline)
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_INLINE_IMAGE_BYTES = 5 * 1024 * 1024
AUTH_TOKEN_STORAGE_KEY = "discirdapp.google_auth_token"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URL = os.getenv("GOOGLE_REDIRECT_URL", "").strip()

HISTORY_FILE = Path(__file__).resolve().with_name("chat_history.json")
HISTORY_DB_FILE = Path(__file__).resolve().with_name("chat_history.duckdb")


@dataclass
class Message:  # noqa: B903 (variável de classe mutável intencional para reaction_users)
    user_name: str
    text: str
    message_type: str
    room_name: str
    message_id: str = ""
    tab_id: str = ""
    target_message_id: str = ""
    reaction_request_id: str = ""
    reaction_type: str = ""
    reaction_action: str = ""
    reaction_users: dict[str, list[str]] = field(default_factory=dict)
    attachment_name: str = ""
    attachment_mime: str = ""
    attachment_data: str = ""
    attachment_size: int = 0
    edited: bool = False
    deleted_for_all: bool = False
    recipient_name: str = ""


REACTIONS = {
    "laugh": "😂",
    "cry": "😢",
    "heart": "❤️",
    "cool": "👍",
}

EMOJI_SHORTCUTS = [
    "😀", "😁", "😂", "🤣", "😊", "😍", "😎", "🤔", "😢", "😭",
    "😡", "👍", "👎", "👏", "🙏", "🔥", "💯", "🎉", "❤️", "💡",
]

AVATAR_COLORS = [
    ft.Colors.AMBER,
    ft.Colors.BLUE,
    ft.Colors.BROWN,
    ft.Colors.CYAN,
    ft.Colors.GREEN,
    ft.Colors.INDIGO,
    ft.Colors.LIME,
    ft.Colors.ORANGE,
    ft.Colors.PINK,
    ft.Colors.PURPLE,
    ft.Colors.RED,
    ft.Colors.TEAL,
    ft.Colors.YELLOW,
]

CHAT_BACKGROUND_PRESETS = [
    ("", "Sem fundo"),
    ("social_life.png", "Social Life"),
    ("Medieval.png", "Medieval"),
    ("Medieval_Beach.png", "Medieval Beach"),
]


def avatar_color_for_user(user_name: str) -> str:
    normalized = (user_name or "").strip().lower() or "unknown"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(AVATAR_COLORS)
    return AVATAR_COLORS[index]


MOBILE_LAYOUT_BREAKPOINT = 900

@ft.control
class ChatMessage(ft.Row):
    def __init__(
        self,
        message: Message,
        on_react,
        attachment_preview: ft.Control | None = None,
        can_manage: bool = False,
        on_manage_message=None,
        on_user_click=None,
    ):
        super().__init__()
        self.message = message
        self.on_react = on_react
        self.vertical_alignment = ft.CrossAxisAlignment.START

        reaction_buttons: list[ft.Control] = []
        for reaction_key, emoji in REACTIONS.items():
            count = len(self.message.reaction_users.get(reaction_key, []))
            reaction_buttons.append(
                ft.TextButton(
                    content=ft.Text(f"{emoji} {count}", size=12),
                    on_click=lambda e, key=reaction_key: self.on_react(self.message.message_id, key),
                )
            )

        header_row_controls: list[ft.Control] = [
            ft.Container(
                content=ft.Text(
                    self.message.user_name,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.GREEN_800,
                ),
                on_click=lambda _e: on_user_click(self.message.user_name) if on_user_click else None,
            )
        ]
        if can_manage and on_manage_message and self.message.message_id:
            header_row_controls.append(
                ft.IconButton(
                    icon=ft.Icons.MORE_VERT,
                    icon_size=14,
                    tooltip="Opções",
                    on_click=lambda _e, msg_id=self.message.message_id: on_manage_message(msg_id),
                )
            )

        message_controls: list[ft.Control] = [
            ft.Row(controls=header_row_controls, tight=True, spacing=4)
        ]

        bubble_controls: list[ft.Control] = []

        if self.message.text.strip() and not self.message.attachment_name:
            bubble_controls.append(ft.Text(self.message.text, selectable=True, color=ft.Colors.WHITE_70))

        if self.message.edited and not self.message.deleted_for_all:
            bubble_controls.append(ft.Text("editada", size=10, italic=True, color=ft.Colors.WHITE_54))

        if attachment_preview:
            bubble_controls.append(attachment_preview)
        bubble_controls.append(ft.Row(controls=reaction_buttons, spacing=4, wrap=True))

        message_controls.append(
            ft.Container(
                content=ft.Column(controls=bubble_controls, spacing=6, tight=True),
                bgcolor=ft.Colors.BLUE_GREY_900,
                border_radius=12,
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            )
        )

        avatar_circle = ft.CircleAvatar()
        avatar_circle.content = ft.Text(self.get_initials(self.message.user_name))
        avatar_circle.color = ft.Colors.WHITE
        avatar_circle.bgcolor = self.get_avatar_color(self.message.user_name)

        avatar = ft.Container(
            content=avatar_circle,
            on_click=lambda _e: on_user_click(self.message.user_name) if on_user_click else None,
        )

        self.controls = [
            avatar,
            ft.Column(
                tight=True,
                spacing=5,
                controls=message_controls,
            ),
        ]

    def get_initials(self, user_name: str):
        if user_name:
            return user_name[:1].capitalize()
        else:
            return "Unk"  # Retorna "Unk" para nomes vazios ou nulos

    def get_avatar_color(self, user_name: str):
        return avatar_color_for_user(user_name)

# Função principal
def main(page: ft.Page):
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.padding = 0
    page.spacing = 0
    page.title = "Flet Chat"

    # Variáveis de estado
    topic = "__rooms__"
    rooms: list[str] = []
    subscribed_rooms: set[str] = set()
    subscribed_private_topics: set[str] = set()
    room_history: dict[str, list[Message]] = {}
    room_users_by_room: dict[str, set[str]] = {}
    hidden_message_ids_by_room: dict[str, set[str]] = {}
    processed_reaction_requests: set[str] = set()
    current_room = ""
    active_user_name = ""
    login_bootstrapped = False
    topic_subscribed = False
    tab_id = uuid.uuid4().hex
    selected_message_id = ""
    editing_message_id = ""
    # Estado para mensagens privadas
    dm_conversations: dict[str, list[Message]] = {}
    current_dm_user = ""
    selected_dm_user = ""
    dm_unread_by_user: dict[str, int] = {}
    left_nav_mode = "rooms"
    history_loaded = False
    current_chat_background = ""
    current_layout_mode = "desktop"
    mobile_active_panel = "chat"
    dm_recipient_input = ft.TextField(label="Mensagem privada", multiline=True, min_lines=1, max_lines=4)
    login_feedback = ft.Text("", color=ft.Colors.RED_300, size=12)
    
    create_room_btn: ft.FilledButton
    image_preview_dlg: ft.AlertDialog
    emoji_picker_dlg: ft.AlertDialog
    settings_dlg: ft.AlertDialog

    # Funções auxiliares
    def open_dialog(dialog: ft.DialogControl):
        dialog.open = True
        page.update()
        
    def close_dialog(dialog: ft.DialogControl):
        dialog.open = False
        page.update()
    
    # Valida o nome de utilizador atraves do armazenamento da sessão, garantindo que é uma string não vazia    
    def auth_user_name() -> str:
        auth = getattr(page, "auth", None)
        if not auth:
            return ""

        user = getattr(auth, "user", None)
        if isinstance(user, dict):
            for key in ("name", "email", "given_name", "preferred_username", "login", "username", "sub", "id"):
                value = str(user.get(key) or "").strip()
                if value:
                    return value
            return ""

        for attr in ("name", "email", "given_name", "preferred_username", "login", "username", "sub", "id"):
            value = str(getattr(user, attr, "") or "").strip()
            if value:
                return value
        return ""

    def valid_user_name() -> str:
        if active_user_name:
            return active_user_name

        auth_name = auth_user_name()
        if auth_name:
            return auth_name
        return ""

    def is_logged_in() -> bool:
        return bool(valid_user_name())
    
    # Normaliza o nome da sala para garantir consistência (removendo espaços e convertendo em minusculas)
    def normalize_room_name(value: str) -> str:
        return (value or "").strip().lower()

    def message_to_dict(message: Message) -> dict:
        return {
            "user_name": message.user_name,
            "text": message.text,
            "message_type": message.message_type,
            "room_name": message.room_name,
            "message_id": message.message_id,
            "tab_id": message.tab_id,
            "target_message_id": message.target_message_id,
            "reaction_request_id": message.reaction_request_id,
            "reaction_type": message.reaction_type,
            "reaction_action": message.reaction_action,
            "reaction_users": {k: list(v) for k, v in message.reaction_users.items()},
            "attachment_name": message.attachment_name,
            "attachment_mime": message.attachment_mime,
            "attachment_data": message.attachment_data,
            "attachment_size": message.attachment_size,
            "edited": message.edited,
            "deleted_for_all": message.deleted_for_all,
            "recipient_name": message.recipient_name,
        }

    def message_from_dict(raw: dict, fallback_room: str = "") -> Message:
        reaction_users_raw = dict(raw.get("reaction_users") or {})
        reaction_users: dict[str, list[str]] = {}
        for key, values in reaction_users_raw.items():
            reaction_users[str(key)] = [str(value) for value in list(values or [])]

        return Message(
            user_name=str(raw.get("user_name") or "Unk"),
            text=str(raw.get("text") or ""),
            message_type=str(raw.get("message_type") or "chat_message"),
            room_name=str(raw.get("room_name") or fallback_room or ""),
            message_id=str(raw.get("message_id") or uuid.uuid4().hex),
            tab_id=str(raw.get("tab_id") or ""),
            target_message_id=str(raw.get("target_message_id") or ""),
            reaction_request_id=str(raw.get("reaction_request_id") or ""),
            reaction_type=str(raw.get("reaction_type") or ""),
            reaction_action=str(raw.get("reaction_action") or ""),
            reaction_users=reaction_users,
            attachment_name=str(raw.get("attachment_name") or ""),
            attachment_mime=str(raw.get("attachment_mime") or ""),
            attachment_data=str(raw.get("attachment_data") or ""),
            attachment_size=int(raw.get("attachment_size") or 0),
            edited=bool(raw.get("edited") or False),
            deleted_for_all=bool(raw.get("deleted_for_all") or False),
            recipient_name=str(raw.get("recipient_name") or ""),
        )

    def init_room_users(room_name: str):
        if room_name not in room_users_by_room:
            room_users_by_room[room_name] = set()

    def track_room_user(room_name: str, user_name: str):
        room = normalize_room_name(room_name)
        user = (user_name or "").strip()
        if not room or not user or user.lower() == "system":
            return
        init_room_users(room)
        room_users_by_room[room].add(user)

    def persist_history():
        payload = {
            "version": 1,
            "rooms": sorted(set(rooms), key=str.lower),
            "room_history": {
                room_name: [message_to_dict(msg) for msg in messages]
                for room_name, messages in room_history.items()
            },
            "dm_conversations": {
                dm_key: [message_to_dict(msg) for msg in messages]
                for dm_key, messages in dm_conversations.items()
            },
            "hidden_message_ids_by_room": {
                room_name: sorted(list(hidden_ids))
                for room_name, hidden_ids in hidden_message_ids_by_room.items()
            },
        }

        def save_payload_to_duckdb(data: dict) -> bool:
            if not duckdb:
                return False

            try:
                connection = duckdb.connect(str(HISTORY_DB_FILE))
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chat_state (
                        state_key VARCHAR PRIMARY KEY,
                        payload_json TEXT,
                        updated_at TIMESTAMP DEFAULT now()
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO chat_state (state_key, payload_json, updated_at)
                    VALUES ('global', ?, now())
                    ON CONFLICT(state_key) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        updated_at = now()
                    """,
                    [json.dumps(data, ensure_ascii=False)],
                )
                connection.close()
                return True
            except Exception:
                return False

        if save_payload_to_duckdb(payload):
            return

        temp_file = HISTORY_FILE.with_suffix(".tmp")
        try:
            temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_file.replace(HISTORY_FILE)
        except OSError:
            pass

    def load_persisted_history():
        nonlocal history_loaded
        if history_loaded:
            return

        history_loaded = True

        raw_data: dict = {}

        if duckdb and HISTORY_DB_FILE.exists():
            try:
                connection = duckdb.connect(str(HISTORY_DB_FILE))
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chat_state (
                        state_key VARCHAR PRIMARY KEY,
                        payload_json TEXT,
                        updated_at TIMESTAMP DEFAULT now()
                    )
                    """
                )
                row = connection.execute(
                    "SELECT payload_json FROM chat_state WHERE state_key='global'"
                ).fetchone()
                connection.close()
                if row and row[0]:
                    raw_data = json.loads(str(row[0]))
            except Exception:
                raw_data = {}

        if not raw_data and HISTORY_FILE.exists():
            try:
                raw_data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))

                # Migração automática: JSON antigo -> DuckDB.
                if duckdb:
                    try:
                        connection = duckdb.connect(str(HISTORY_DB_FILE))
                        connection.execute(
                            """
                            CREATE TABLE IF NOT EXISTS chat_state (
                                state_key VARCHAR PRIMARY KEY,
                                payload_json TEXT,
                                updated_at TIMESTAMP DEFAULT now()
                            )
                            """
                        )
                        connection.execute(
                            """
                            INSERT INTO chat_state (state_key, payload_json, updated_at)
                            VALUES ('global', ?, now())
                            ON CONFLICT(state_key) DO UPDATE SET
                                payload_json = excluded.payload_json,
                                updated_at = now()
                            """,
                            [json.dumps(raw_data, ensure_ascii=False)],
                        )
                        connection.close()
                    except Exception:
                        pass
            except (OSError, json.JSONDecodeError):
                raw_data = {}

        if not raw_data:
            if "geral" not in rooms:
                rooms.append("geral")
            if "geral" not in room_history:
                room_history["geral"] = []
            init_room_users("geral")
            init_hidden_ids("geral")
            return

        loaded_rooms = list(raw_data.get("rooms") or [])
        for raw_room in loaded_rooms:
            room = normalize_room_name(str(raw_room))
            if not room:
                continue
            if room not in rooms:
                rooms.append(room)
            if room not in room_history:
                room_history[room] = []
            init_room_users(room)
            init_hidden_ids(room)

        loaded_room_history = dict(raw_data.get("room_history") or {})
        for raw_room_name, raw_messages in loaded_room_history.items():
            room_name = normalize_room_name(str(raw_room_name))
            if not room_name:
                continue
            if room_name not in rooms:
                rooms.append(room_name)
            parsed_messages: list[Message] = []
            for raw_message in list(raw_messages or []):
                if isinstance(raw_message, dict):
                    parsed_message = message_from_dict(raw_message, fallback_room=room_name)
                    parsed_messages.append(parsed_message)
                    if parsed_message.message_type in ("chat_message", "login_message"):
                        track_room_user(room_name, parsed_message.user_name)
            room_history[room_name] = parsed_messages
            init_room_users(room_name)
            init_hidden_ids(room_name)

        loaded_dm_history = dict(raw_data.get("dm_conversations") or {})
        for raw_dm_key, raw_messages in loaded_dm_history.items():
            dm_key = str(raw_dm_key or "")
            if not dm_key:
                continue
            parsed_messages: list[Message] = []
            for raw_message in list(raw_messages or []):
                if isinstance(raw_message, dict):
                    parsed_messages.append(message_from_dict(raw_message))
            dm_conversations[dm_key] = parsed_messages

        loaded_hidden_ids = dict(raw_data.get("hidden_message_ids_by_room") or {})
        for raw_room_name, raw_hidden_ids in loaded_hidden_ids.items():
            room_name = normalize_room_name(str(raw_room_name))
            if not room_name:
                continue
            init_hidden_ids(room_name)
            hidden_message_ids_by_room[room_name] = {
                str(message_id)
                for message_id in list(raw_hidden_ids or [])
                if str(message_id)
            }

        if "geral" not in rooms:
            rooms.append("geral")
        if "geral" not in room_history:
            room_history["geral"] = []
        init_room_users("geral")
        init_hidden_ids("geral")

    # Atualiza membros visíveis da sala atual
    def refresh_users_sidebar():
        init_room_users(current_room)
        users = sorted(room_users_by_room.get(current_room, set()), key=str.lower)
        users_col.controls = []
        if not users:
            users_col.controls.append(ft.Text("Sem utilizadores visíveis", size=12, color=ft.Colors.WHITE_54))
            return

        for user_name in users:
            user_avatar = ft.CircleAvatar()
            user_avatar.radius = 12
            user_avatar.content = ft.Text(user_name[:1].upper() if user_name else "?", size=10)
            user_avatar.color = ft.Colors.WHITE
            user_avatar.bgcolor = avatar_color_for_user(user_name)

            users_col.controls.append(
                ft.TextButton(
                    content=ft.Row(
                        controls=[
                            user_avatar,
                            ft.Text(user_name),
                        ],
                        spacing=8,
                    ),
                    style=ft.ButtonStyle(padding=8),
                    on_click=lambda _e, target=user_name: open_dm_dialog(target),
                )
            )

    # Chave canônica para um par de utilizadores
    def dm_key_for(peer_name: str) -> str:
        me = valid_user_name() or ""
        peer = (peer_name or "").strip()
        if not me or not peer:
            return ""
        pair = sorted([me, peer], key=str.lower)
        return f"{pair[0]}|{pair[1]}"

    # Sidebar de DMs com badge de não lidas
    def refresh_dm_sidebar():
        me = valid_user_name() or ""
        dm_col.controls = []

        peers: set[str] = set(dm_unread_by_user.keys())
        for key in dm_conversations:
            if "|" not in key:
                continue
            left, right = key.split("|", 1)
            if left == me:
                peers.add(right)
            elif right == me:
                peers.add(left)

        ordered_peers = sorted(peers, key=str.lower)
        if not ordered_peers:
            dm_col.controls.append(ft.Text("Sem DMs", size=12, color=ft.Colors.WHITE_54))
            update_dm_tab_badge()
            return

        for peer in ordered_peers:
            unread = dm_unread_by_user.get(peer, 0)
            badge = ft.Container(
                content=ft.Text(str(unread), size=10, color=ft.Colors.WHITE),
                bgcolor=ft.Colors.RED_500,
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                visible=unread > 0,
            )
            badge_slot = ft.Container(
                width=34,
                content=ft.Row(
                    controls=[badge],
                    alignment=ft.MainAxisAlignment.END,
                    tight=True,
                ),
            )
            peer_avatar = ft.CircleAvatar()
            peer_avatar.radius = 12
            peer_avatar.content = ft.Text(peer[:1].upper() if peer else "?", size=10)
            peer_avatar.color = ft.Colors.WHITE
            peer_avatar.bgcolor = avatar_color_for_user(peer)

            dm_col.controls.append(
                ft.TextButton(
                    content=ft.Row(
                        controls=[
                            peer_avatar,
                            ft.Container(
                                content=ft.Text(
                                    peer,
                                    weight=ft.FontWeight.W_500,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                tooltip=peer,
                                expand=True,
                            ),
                            badge_slot,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.BLUE_GREY_800 if peer == selected_dm_user else None,
                        padding=8,
                    ),
                    on_click=lambda _e, target=peer: open_dm_thread(target),
                )
            )

        update_dm_tab_badge()

    def update_dm_tab_badge():
        total_unread = sum(max(0, int(count)) for count in dm_unread_by_user.values())
        dm_tab_badge_text.value = str(total_unread)
        dm_tab_badge.visible = total_unread > 0

    def refresh_left_sidebar():
        rooms_nav_panel.visible = left_nav_mode == "rooms"
        dms_nav_panel.visible = left_nav_mode == "dms"
        room_tab_btn.style = ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_400 if left_nav_mode == "rooms" else ft.Colors.GREY_800,
            color=ft.Colors.WHITE,
            padding=8,
        )
        dm_tab_btn.style = ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_400 if left_nav_mode == "dms" else ft.Colors.GREY_800,
            color=ft.Colors.WHITE,
            padding=8,
        )

    def show_left_nav(mode: str):
        nonlocal left_nav_mode
        left_nav_mode = mode if mode in {"rooms", "dms"} else "rooms"
        refresh_left_sidebar()
        page.update()

    def open_dm_thread(peer_name: str):
        nonlocal selected_dm_user
        peer = (peer_name or "").strip()
        if not peer or peer == (valid_user_name() or ""):
            return
        selected_dm_user = peer
        dm_unread_by_user[peer] = 0
        room_badge.value = f"Conversa privada: {peer}"
        new_message.hint_text = f"Mensagem privada para {peer}"
        load_room_messages()
        refresh_dm_sidebar()
        page.update()

    def ensure_reactions(message: Message):
        for reaction_key in REACTIONS:
            if reaction_key not in message.reaction_users:
                message.reaction_users[reaction_key] = []

    def init_hidden_ids(room_name: str):
        if room_name not in hidden_message_ids_by_room:
            hidden_message_ids_by_room[room_name] = set()

    def is_hidden(room_name: str, message_id: str) -> bool:
        init_hidden_ids(room_name)
        return bool(message_id and message_id in hidden_message_ids_by_room[room_name])

    def is_own_message(message: Message) -> bool:
        if message.tab_id and message.tab_id == tab_id:
            return True
        return bool(message.user_name and message.user_name == (valid_user_name() or ""))

    def find_message(room_name: str, message_id: str) -> Message | None:
        for existing_message in room_history.get(room_name, []):
            if existing_message.message_id == message_id:
                return existing_message
        return None

    def find_dm_message(message_id: str) -> tuple[str, Message] | None:
        for dm_key, dm_messages in dm_conversations.items():
            for existing_message in dm_messages:
                if existing_message.message_id == message_id:
                    return dm_key, existing_message
        return None

    def apply_reaction_to_message(message: Message, reacting_tab_id: str, reaction_key: str, reaction_action: str):
        ensure_reactions(message)
        if reaction_action == "remove":
            remove_reaction(message, reacting_tab_id, reaction_key)
        else:
            add_reaction(message, reacting_tab_id, reaction_key)

    def apply_reaction_to_dm_message(target_message_id: str, reacting_tab_id: str, reaction_key: str, reaction_action: str) -> bool:
        dm_match = find_dm_message(target_message_id)
        if not dm_match:
            return False

        dm_key, target_message = dm_match
        apply_reaction_to_message(target_message, reacting_tab_id, reaction_key, reaction_action)
        dm_conversations[dm_key] = list(dm_conversations.get(dm_key, []))
        persist_history()
        return True

    def update_dm_message_text(target_message_id: str, new_text: str, deleted_for_all: bool = False) -> bool:
        dm_match = find_dm_message(target_message_id)
        if not dm_match:
            return False

        dm_key, target_message = dm_match
        target_message.text = new_text
        target_message.edited = not deleted_for_all and bool(new_text)
        target_message.deleted_for_all = deleted_for_all
        if deleted_for_all:
            target_message.attachment_name = ""
            target_message.attachment_mime = ""
            target_message.attachment_data = ""
            target_message.attachment_size = 0
        dm_conversations[dm_key] = list(dm_conversations.get(dm_key, []))
        persist_history()
        return True

    def can_manage(request_user_name: str, request_tab_id: str, target_message: Message) -> bool:
        if request_tab_id and target_message.tab_id:
            return request_tab_id == target_message.tab_id
        return bool(request_user_name and request_user_name == target_message.user_name)

    preview_image_title = ft.Text("", weight=ft.FontWeight.BOLD)
    preview_image = ft.Image(src="", width=900, height=600, fit=ft.BoxFit.CONTAIN)

    image_preview_dlg = ft.AlertDialog(
        open=False,
        modal=True,
        title=preview_image_title,
        content=ft.Container(content=preview_image, width=900, height=600),
        actions=[ft.TextButton("Fechar", on_click=lambda _: close_dialog(image_preview_dlg))],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    edit_message_input = ft.TextField(label="Nova mensagem", multiline=True, min_lines=1, max_lines=4)

    def close_actions_dlg():
        close_dialog(message_actions_dlg)

    def close_edit_dlg():
        close_dialog(edit_message_dlg)

    async def save_edit(_):
        nonlocal editing_message_id
        new_text = (edit_message_input.value or "").strip()
        if not editing_message_id or not new_text:
            return

        if selected_dm_user:
            updated = update_dm_message_text(editing_message_id, new_text, deleted_for_all=False)
            if updated:
                page.pubsub.send_all_on_topic(
                    selected_dm_user,
                    Message(
                        user_name=valid_user_name() or "Unk",
                        text=new_text,
                        message_type="message_edit",
                        room_name="",
                        target_message_id=editing_message_id,
                        tab_id=tab_id,
                        recipient_name=selected_dm_user,
                    ),
                )
                load_room_messages()
                page.update()
            editing_message_id = ""
            edit_message_input.value = ""
            close_edit_dlg()
            return

        stored_room_name = page.session.store.get("room_name")
        if not isinstance(stored_room_name, str) or not stored_room_name:
            return

        page.pubsub.send_all_on_topic(
            stored_room_name,
            Message(
                user_name=valid_user_name() or "Unk",
                text=new_text,
                message_type="message_edit",
                room_name=stored_room_name,
                target_message_id=editing_message_id,
                tab_id=tab_id,
            ),
        )
        editing_message_id = ""
        edit_message_input.value = ""
        persist_history()
        close_edit_dlg()

    def hide_message(_):
        nonlocal selected_message_id
        if not selected_message_id:
            return

        if selected_dm_user:
            dm_key = dm_key_for(selected_dm_user)
            if not dm_key:
                return
            init_hidden_ids(dm_key)
            hidden_message_ids_by_room[dm_key].add(selected_message_id)
            persist_history()
            selected_message_id = ""
            close_actions_dlg()
            load_room_messages()
            page.update()
            return

        stored_room_name = page.session.store.get("room_name")
        if not isinstance(stored_room_name, str) or not stored_room_name:
            return

        init_hidden_ids(stored_room_name)
        hidden_message_ids_by_room[stored_room_name].add(selected_message_id)
        persist_history()
        selected_message_id = ""
        close_actions_dlg()
        load_room_messages()
        page.update()

    def delete_message(_):
        nonlocal selected_message_id
        if not selected_message_id:
            return

        if selected_dm_user:
            updated = update_dm_message_text(selected_message_id, "Esta mensagem foi apagada.", deleted_for_all=True)
            if updated:
                page.pubsub.send_all_on_topic(
                    selected_dm_user,
                    Message(
                        user_name=valid_user_name() or "Unk",
                        text="",
                        message_type="message_delete_all",
                        room_name="",
                        target_message_id=selected_message_id,
                        tab_id=tab_id,
                        recipient_name=selected_dm_user,
                    ),
                )
                load_room_messages()
                page.update()
            selected_message_id = ""
            close_actions_dlg()
            return

        stored_room_name = page.session.store.get("room_name")
        if not isinstance(stored_room_name, str) or not stored_room_name:
            return

        page.pubsub.send_all_on_topic(
            stored_room_name,
            Message(
                user_name=valid_user_name() or "Unk",
                text="",
                message_type="message_delete_all",
                room_name=stored_room_name,
                target_message_id=selected_message_id,
                tab_id=tab_id,
            ),
        )
        selected_message_id = ""
        close_actions_dlg()

    def edit_message(_):
        nonlocal editing_message_id
        if not selected_message_id:
            return

        if selected_dm_user:
            target_message = find_dm_message(selected_message_id)
            if not target_message or target_message[1].deleted_for_all or target_message[1].attachment_name:
                close_actions_dlg()
                return

            editing_message_id = selected_message_id
            selected_message_text = target_message[1].text or ""
            edit_message_input.value = selected_message_text
            close_actions_dlg()
            open_dialog(edit_message_dlg)
            return

        stored_room_name = page.session.store.get("room_name")
        if not isinstance(stored_room_name, str) or not stored_room_name:
            return

        target_message = find_message(stored_room_name, selected_message_id)
        if not target_message or target_message.deleted_for_all or target_message.attachment_name:
            close_actions_dlg()
            return

        editing_message_id = selected_message_id
        selected_message_text = target_message.text or ""
        edit_message_input.value = selected_message_text
        close_actions_dlg()
        open_dialog(edit_message_dlg)

    def show_actions(message_id: str):
        nonlocal selected_message_id
        selected_message_id = message_id
        open_dialog(message_actions_dlg)

    message_actions_dlg = ft.AlertDialog(
        open=False,
        modal=True,
        title=ft.Text("Opções da mensagem"),
        content=ft.Column(
            controls=[
                ft.TextButton("Editar", on_click=edit_message),
                ft.TextButton("Apagar para mim", on_click=hide_message),
                ft.TextButton("Apagar para todos", on_click=delete_message),
            ],
            tight=True,
        ),
        actions=[ft.TextButton("Cancelar", on_click=lambda _: close_actions_dlg())],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    edit_message_dlg = ft.AlertDialog(
        open=False,
        modal=True,
        title=ft.Text("Editar mensagem"),
        content=ft.Column([edit_message_input], width=420, tight=True),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda _: close_edit_dlg()),
            ft.TextButton("Guardar", on_click=save_edit),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    # Preview de imagens em mensagens, abrindo um dialogo com a imagem em tamanho maior quando clicada
    def show_image(image_name: str, mime_type: str, image_data: str):
        if not image_data:
            return

        preview_image_title.value = image_name or "Imagem"
        preview_image.src = f"data:{mime_type or 'image/png'};base64,{image_data}"
        open_dialog(image_preview_dlg)
    
    # Preview para anexos (mostra o ficheiro e um botao de download)
    def build_attachment_preview(message: Message):
        if not message.attachment_name:
            return None

        if message.attachment_data and message.attachment_mime.startswith("image/"):
            return ft.GestureDetector(
                mouse_cursor=ft.MouseCursor.CLICK,
                on_tap=lambda _e, msg=message: show_image(
                    msg.attachment_name,
                    msg.attachment_mime,
                    msg.attachment_data,
                ),
                content=ft.Image(
                    src=f"data:{message.attachment_mime or 'image/png'};base64,{message.attachment_data}",
                    width=280,
                    fit=ft.BoxFit.CONTAIN,
                ),
            )

        file_label = message.attachment_name
        if message.attachment_size:
            file_label = f"{file_label} ({message.attachment_size} bytes)"

        if not message.attachment_data:
            return ft.Row(
                controls=[
                    ft.Icon(ft.Icons.DOWNLOAD_ROUNDED, size=16, color=ft.Colors.BLUE_300),
                    ft.Text(file_label),
                    ft.Text("anexo sem dados para transferir", size=12, color=ft.Colors.WHITE_70),
                ],
                spacing=6,
                wrap=True,
            )

        async def open_attachment(_):
            if not message.attachment_data:
                show_attachment_error("Este anexo não tem dados para transferir.")
                return

            try:
                file_bytes = base64.b64decode(message.attachment_data)
            except ValueError:
                show_attachment_error("Não foi possível processar este anexo.")
                return

            await file_picker.save_file(
                file_name=message.attachment_name or "anexo",
                src_bytes=file_bytes,
            )

        return ft.Row(
            controls=[
                ft.Icon(ft.Icons.DOWNLOAD_ROUNDED, size=16, color=ft.Colors.BLUE_300),
                ft.Text(message.attachment_name or "ficheiro"),
                ft.TextButton("Transferir", on_click=open_attachment),
            ],
            spacing=6,
            wrap=True,
        )

    def show_attachment_error(message: str):
        open_dialog(ft.SnackBar(content=ft.Text(message)))

    # Funcoes para adicionar e remover reacoes garantindo uma reacao por utilizador
    def add_reaction(message: Message, reacting_tab_id: str, reaction_key: str) -> bool:
        if not message.message_id or reaction_key not in REACTIONS or not reacting_tab_id:
            return False

        ensure_reactions(message)
        users = message.reaction_users[reaction_key]

        if reacting_tab_id not in users:
            users.append(reacting_tab_id)
        return True

    def remove_reaction(message: Message, reacting_tab_id: str, reaction_key: str) -> bool:
        if not message.message_id or reaction_key not in REACTIONS or not reacting_tab_id:
            return False

        ensure_reactions(message)
        users = message.reaction_users[reaction_key]

        #  Toogle por tab_id garantindo uma reacao unica
        if reacting_tab_id in users:
            users.remove(reacting_tab_id) 
        return True

    def react(target_message_id: str, reaction_key: str):
        if not target_message_id or reaction_key not in REACTIONS:
            return

        stored_user_name = valid_user_name() or "Unk"
        reaction_action = "add"
        local_dm_message = None

        if selected_dm_user:
            dm_key = dm_key_for(selected_dm_user)
            for existing_message in dm_conversations.get(dm_key, []):
                if existing_message.message_id == target_message_id:
                    ensure_reactions(existing_message)
                    current_users = existing_message.reaction_users.get(reaction_key, [])
                    reaction_action = "remove" if tab_id in current_users else "add"
                    local_dm_message = existing_message
                    break
        else:
            stored_room_name = page.session.store.get("room_name")
            if not isinstance(stored_room_name, str) or not stored_room_name:
                return

            for existing_message in room_history.get(stored_room_name, []):
                if existing_message.message_id == target_message_id:
                    ensure_reactions(existing_message)
                    current_users = existing_message.reaction_users.get(reaction_key, [])
                    reaction_action = "remove" if tab_id in current_users else "add"
                    break

        if local_dm_message:
            apply_reaction_to_message(local_dm_message, tab_id, reaction_key, reaction_action)
            persist_history()
            load_room_messages()
            refresh_dm_sidebar()
            page.update()
            page.pubsub.send_all_on_topic(
                selected_dm_user,
                Message(
                    user_name=stored_user_name,
                    text="",
                    message_type="reaction_update",
                    room_name="",
                    target_message_id=target_message_id,
                    reaction_type=reaction_key,
                    reaction_action=reaction_action,
                    reaction_request_id=uuid.uuid4().hex,
                    tab_id=tab_id,
                    recipient_name=selected_dm_user,
                ),
            )
            return

        stored_room_name = page.session.store.get("room_name")
        if not isinstance(stored_room_name, str) or not stored_room_name:
            return

        page.pubsub.send_all_on_topic(
            stored_room_name,
            Message(
                user_name=stored_user_name,
                text="",
                message_type="reaction_update",
                room_name=stored_room_name,
                target_message_id=target_message_id,
                reaction_type=reaction_key,
                reaction_action=reaction_action,
                reaction_request_id=uuid.uuid4().hex,
                tab_id=tab_id,
            ),
        )
    
    # Envio de imagens com validacao de tipo e tamanho usando o file picker
    async def send_image_attachment(_):
        stored_room_name = page.session.store.get("room_name")
        if not isinstance(stored_room_name, str) or not stored_room_name:
            return

        # Valida o utilizador antes de enviar
        stored_user_name = valid_user_name()
        if not stored_user_name:
            login_feedback.value = "Inicia sessão para enviar ficheiros."
            open_dialog(welcome_dlg)
            return

        # Abre o file picker para escolher uma imagem
        try:
            files = await file_picker.pick_files(
                allow_multiple=False,
                with_data=True,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["png", "jpg", "jpeg"],
            )
        except RuntimeError:
            show_attachment_error("Não foi possível abrir o seletor de imagens.")
            return

        if not files:
            return

        selected = files[0]
        attachment_name = selected.name
        attachment_mime = mimetypes.guess_type(attachment_name)[0] or "application/octet-stream"
        attachment_size = int(getattr(selected, "size", 0) or 0)

        if attachment_size > MAX_ATTACHMENT_BYTES:
            show_attachment_error("O ficheiro não pode exceder 20MB.")
            return

        if attachment_mime not in {"image/png", "image/jpeg", "image/jpg"}:
            show_attachment_error("Só são permitidas imagens PNG/JPG/JPEG.")
            return

        file_bytes = selected.bytes or b""
        if not file_bytes and selected.path and os.path.exists(selected.path):
            with open(selected.path, "rb") as file_handle:
                file_bytes = file_handle.read()

        if not file_bytes:
            show_attachment_error("Não foi possível ler a imagem selecionada.")
            return

        if attachment_size <= 0:
            attachment_size = len(file_bytes)

        attachment_data = ""
        if attachment_size <= MAX_INLINE_IMAGE_BYTES:
            attachment_data = base64.b64encode(file_bytes).decode("ascii")

        page.pubsub.send_all_on_topic(
            stored_room_name,
            Message(
                user_name=stored_user_name,
                text="",
                message_type="chat_message",
                room_name=stored_room_name,
                message_id=uuid.uuid4().hex,
                tab_id=tab_id,
                reaction_users={key: [] for key in REACTIONS},
                attachment_name=attachment_name,
                attachment_mime=attachment_mime,
                attachment_data=attachment_data,
                attachment_size=attachment_size,
            ),
        )
        page.update()

    async def send_zip_attachment(_):
        stored_room_name = page.session.store.get("room_name")
        if not isinstance(stored_room_name, str) or not stored_room_name:
            return

        stored_user_name = valid_user_name()
        if not stored_user_name:
            login_feedback.value = "Inicia sessão com Google para enviar ficheiros."
            open_dialog(welcome_dlg)
            return

        try:
            files = await file_picker.pick_files(
                allow_multiple=False,
                with_data=True,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["zip"],
            )
        except RuntimeError:
            show_attachment_error("Não foi possível abrir o seletor de ZIP.")
            return

        if not files:
            return

        # Validar o ficheiro selecionado
        selected = files[0]
        attachment_name = selected.name
        if os.path.splitext(attachment_name)[1].lower() != ".zip":
            show_attachment_error("Só são permitidos ficheiros ZIP.")
            return

        attachment_size = int(getattr(selected, "size", 0) or 0)
        if attachment_size > MAX_ATTACHMENT_BYTES:
            show_attachment_error("O ficheiro ZIP não pode exceder 20MB.")
            return

        file_bytes = selected.bytes or b""
        if not file_bytes and selected.path and os.path.exists(selected.path):
            with open(selected.path, "rb") as file_handle:
                file_bytes = file_handle.read()

        if not file_bytes:
            show_attachment_error("Não foi possível ler o ZIP selecionado.")
            return

        if attachment_size <= 0:
            attachment_size = len(file_bytes)

        attachment_data = base64.b64encode(file_bytes).decode("ascii")

        page.pubsub.send_all_on_topic(
            stored_room_name,
            Message(
                user_name=stored_user_name,
                text="",
                message_type="chat_message",
                room_name=stored_room_name,
                message_id=uuid.uuid4().hex,
                tab_id=tab_id,
                reaction_users={key: [] for key in REACTIONS},
                attachment_name=attachment_name,
                attachment_mime="application/zip",
                attachment_data=attachment_data,
                attachment_size=attachment_size,
            ),
        )
        page.update()

    # Controlo de mensagem (formatação diferente para mensagens de chat e de sistema)
    def message_control(message: Message):
        if message.message_type in ("chat_message", "direct_message"):
            ensure_reactions(message)
            attachment_preview = build_attachment_preview(message)
            return ChatMessage(
                message,
                on_react=react,
                attachment_preview=attachment_preview,
                can_manage=is_own_message(message) and not message.deleted_for_all,
                on_manage_message=show_actions,
                on_user_click=open_dm_dialog,
            )
        return ft.Text(
            message.text,
            style=ft.TextStyle(italic=True),
            color=ft.Colors.BLUE_700,
            size=12,
        )

    def scroll_chat_to_latest():
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
            return

        loop.create_task(chat.scroll_to(offset=-1))
        
    # Atualiza painel central conforme o contexto
    def load_room_messages():
        chat.controls.clear()

        if selected_dm_user:
            dm_key = dm_key_for(selected_dm_user)
            for message in dm_conversations.get(dm_key, []):
                if is_hidden(dm_key, message.message_id):
                    continue
                chat.controls.append(message_control(message))
            refresh_dm_sidebar()
            scroll_chat_to_latest()
            return

        for message in room_history.get(current_room, []):
            if is_hidden(current_room, message.message_id):
                continue
            chat.controls.append(message_control(message))
        refresh_users_sidebar()
        scroll_chat_to_latest()

    def update_rooms():
        room_controls: list[ft.Control] = [
            ft.TextButton(
                content=ft.Text(room_name),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_400 if room_name == current_room and not selected_dm_user else None,
                    color=ft.Colors.WHITE,
                    padding=8,
                ),
                on_click=lambda e, selected_room=room_name: open_room_thread(selected_room),
            )
            for room_name in rooms
        ]
        rooms_col.controls = room_controls
        refresh_dm_sidebar()

    def open_room_thread(room_name: str):
        nonlocal selected_dm_user
        selected_dm_user = ""
        switch_room(room_name)

    # Garante que o utilizador esteja subscrito ao topico principal
    def topic_subscription():
        nonlocal topic_subscribed
        if topic_subscribed:
            return

        page.pubsub.subscribe_topic(topic, on_message)
        topic_subscribed = True

    def ensure_private_subscription(user_name: str):
        user = (user_name or "").strip()
        if not user or user in subscribed_private_topics:
            return
        page.pubsub.subscribe_topic(user, on_message)
        subscribed_private_topics.add(user)

    # Verifica se a sala existe e se nao cria e subscreve o utilizador
    def verify_room(room_name: str):
        room = normalize_room_name(room_name)
        if not room:
            return ""

        was_new_room = room not in rooms
        if room not in rooms:
            rooms.append(room)

        if room not in subscribed_rooms:
            page.pubsub.subscribe_topic(room, on_message)
            subscribed_rooms.add(room)

        if room not in room_history:
            room_history[room] = []
        init_room_users(room)
        init_hidden_ids(room)

        if was_new_room:
            persist_history()

        update_rooms()
        return room

    def switch_room(room_name: str):
        nonlocal current_room, selected_dm_user
        room = verify_room(room_name)
        if not room:
            return

        selected_dm_user = ""
        current_room = room
        page.session.store.set("room_name", current_room)
        room_badge.value = f"Sala atual: {current_room}"

        stored_user_name = valid_user_name() or "Unk"
        track_room_user(current_room, stored_user_name)
        new_message.hint_text = f"Mensagem para {stored_user_name}@{current_room}"

        load_room_messages()
        update_rooms()
        send_presence_announce(current_room)
        request_room_presence(current_room)

    # Sincroniza presença entre sessões
    def send_presence_announce(room_name: str, recipient_name: str = ""):
        stored_user_name = valid_user_name()
        room = normalize_room_name(room_name)
        if not stored_user_name or not room:
            return

        page.pubsub.send_all_on_topic(
            room,
            Message(
                user_name=stored_user_name,
                text="",
                message_type="presence_announce",
                room_name=room,
                recipient_name=recipient_name,
                tab_id=tab_id,
            ),
        )

    def request_room_presence(room_name: str):
        stored_user_name = valid_user_name()
        room = normalize_room_name(room_name)
        if not stored_user_name or not room:
            return

        page.pubsub.send_all_on_topic(
            room,
            Message(
                user_name=stored_user_name,
                text="",
                message_type="presence_request",
                room_name=room,
                recipient_name=stored_user_name,
                tab_id=tab_id,
            ),
        )

    def complete_google_login(show_error: bool = True) -> bool:
        nonlocal active_user_name, login_bootstrapped
        user_name = valid_user_name()
        if not user_name:
            if show_error:
                login_feedback.value = "Não foi possível fazer login."
                page.update()
            return False

        if login_bootstrapped and active_user_name == user_name:
            close_dialog(welcome_dlg)
            return True

        login_feedback.value = ""
        active_user_name = user_name
        page.session.store.set("user_name", user_name)
        close_dialog(welcome_dlg)

        topic_subscription()
        # Subscrever ao tópico pessoal (para receber mensagens privadas)
        ensure_private_subscription(user_name)
        load_persisted_history()
        
        default_room = verify_room("geral")
        switch_room(default_room)
        page.pubsub.send_all_on_topic(
            default_room,
            Message(
                user_name=user_name,
                text=f"{user_name} juntou-se à sala '{default_room}'.",
                message_type="login_message",
                room_name=default_room,
            ),
        )
        new_message.disabled = False
        create_room_btn.disabled = False
        login_bootstrapped = True
        page.update()
        return True

    async def save_auth_token():
        auth = getattr(page, "auth", None)
        token = getattr(auth, "token", None) if auth else None
        if not token:
            return

        try:
            await page.shared_preferences.set(AUTH_TOKEN_STORAGE_KEY, token.to_json())
        except Exception:
            # If storage is unavailable, keep runtime login flow working.
            pass

    async def restore_auth_token_if_available():
        if not google_provider:
            return

        try:
            saved = await page.shared_preferences.get(AUTH_TOKEN_STORAGE_KEY)
        except Exception:
            return

        if isinstance(saved, str) and saved.strip():
            try:
                await page.login(provider=google_provider, saved_token=saved.strip())
            except Exception:
                pass

    async def clear_saved_auth_token():
        try:
            await page.shared_preferences.remove(AUTH_TOKEN_STORAGE_KEY)
        except Exception:
            pass

    google_provider = None
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URL:
        google_provider = GoogleOAuthProvider(
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            redirect_url=GOOGLE_REDIRECT_URL,
        )

    def is_ios_web() -> bool:
        user_agent = str(getattr(page, "client_user_agent", "") or "").lower()
        return page.web and ("iphone" in user_agent or "ipad" in user_agent or "ipod" in user_agent)

    async def open_authorization_url_same_tab(url: str):
        await page.launch_url(
            url,
            web_popup_window=True,
            web_popup_window_name=ft.UrlTarget.SELF,
        )

    async def google_login_click(_):
        if not google_provider:
            login_feedback.value = "Configura GOOGLE_* e usa /oauth_callback no GOOGLE_REDIRECT_URL."
            page.update()
            return

        login_feedback.value = ""

        try:
            if page.web:
                if is_ios_web():
                    await page.login(
                        provider=google_provider,
                        redirect_to_page=True,
                        on_open_authorization_url=open_authorization_url_same_tab,
                    )
                    return

                await page.login(provider=google_provider, redirect_to_page=False)
                return

            await page.login(provider=google_provider, redirect_to_page=False)
        except Exception as ex:
            login_feedback.value = f"Erro ao abrir login: {ex}"
            page.update()

    async def finalize_google_login_with_retry():
        for _ in range(100):
            if complete_google_login(show_error=False):
                page.run_task(save_auth_token)
                return
            await asyncio.sleep(0.2)
        login_feedback.value = "Não foi possível fazer login."
        page.update()

    async def recover_session_with_retry():
        await restore_auth_token_if_available()
        for _ in range(40):
            if complete_google_login(show_error=False):
                page.run_task(save_auth_token)
                return
            await asyncio.sleep(0.2)
        login_feedback.value = ""
        open_dialog(welcome_dlg)

    def on_page_connect(_):
        if not page.web or is_logged_in():
            return
        login_feedback.value = "A recuperar sessão..."
        open_dialog(welcome_dlg)
        page.run_task(recover_session_with_retry)

    def on_oauth_login(e):
        if getattr(e, "error", ""):
            login_feedback.value = f"Falha no login: {e.error}"
            page.update()
            return
        if not complete_google_login(show_error=False):
            login_feedback.value = "A finalizar login Google..."
            page.update()
            asyncio.create_task(finalize_google_login_with_retry())
            return
        page.run_task(save_auth_token)

    def create_room_click(e):
        if not is_logged_in():
            open_dialog(welcome_dlg)
            return

        room_name = normalize_room_name(create_room_name.value or "")
        if not room_name:
            create_room_name.error = "O nome da sala não pode estar vazio."
            page.update()
            return

        create_room_name.error = None
        create_room_name.value = ""
        close_dialog(create_room_dlg)

        switch_room(room_name)

        stored_user_name = page.session.store.get("user_name")
        if not isinstance(stored_user_name, str) or not stored_user_name:
            stored_user_name = "Unk"

        page.pubsub.send_all_on_topic(
            room_name,
            Message(
                user_name="System",
                text=f"{stored_user_name} abriu a sala '{room_name}'.",
                message_type="login_message",
                room_name=room_name,
            ),
        )
        page.pubsub.send_all_on_topic(
            topic,
            Message(
                user_name="System",
                text=f"Sala '{room_name}' criada.",
                message_type="room_created",
                room_name=room_name,
            ),
        )
        page.update()

    def open_create_room_dlg(e):
        if not is_logged_in():
            open_dialog(welcome_dlg)
            return

        create_room_name.error = None
        create_room_name.value = ""
        open_dialog(create_room_dlg)

    # Envia mensagem para sala ou DM ativa
    async def send_message_click(e):
        message_text = (new_message.value or "").strip()
        if not message_text:
            return

        stored_user_name = valid_user_name()
        if not stored_user_name:
            login_feedback.value = "Inicia sessão com Google para enviar mensagens."
            open_dialog(welcome_dlg)
            return

        if selected_dm_user:
            msg = Message(
                user_name=stored_user_name,
                text=message_text,
                message_type="direct_message",
                room_name="",
                message_id=uuid.uuid4().hex,
                tab_id=tab_id,
                recipient_name=selected_dm_user,
                reaction_users={key: [] for key in REACTIONS},
            )
            dm_key = dm_key_for(selected_dm_user)
            if dm_key not in dm_conversations:
                dm_conversations[dm_key] = []
            ensure_reactions(msg)
            dm_conversations[dm_key].append(msg)
            persist_history()
            page.pubsub.send_all_on_topic(selected_dm_user, msg)
            load_room_messages()
            refresh_dm_sidebar()
        else:
            stored_room_name = page.session.store.get("room_name")
            if not isinstance(stored_room_name, str) or not stored_room_name:
                return

            page.pubsub.send_all_on_topic(
                stored_room_name,
                Message(
                    user_name=stored_user_name,
                    text=message_text,
                    message_type="chat_message",
                    room_name=stored_room_name,
                    message_id=uuid.uuid4().hex,
                    tab_id=tab_id,
                    reaction_users={key: [] for key in REACTIONS},
                ),
            )
        new_message.value = ""
        await new_message.focus()
        page.update()

    # Função para lidar com mensagens recebidas
    def on_message(*args):
        message: Message | dict
        topic_from_event = ""

        if len(args) == 1:
            message = args[0]
        elif len(args) == 2:
            topic_from_event = str(args[0] or "")
            message = args[1]
        else:
            return

        if not isinstance(message, (Message, dict)):
            return

        if isinstance(message, dict):
            message_type = str(message.get("message_type") or "chat_message")
            message_room = str(message.get("room_name") or "")
            
            if message_type == "direct_message":
                recipient_name = str(message.get("recipient_name") or "")
                sender_name = str(message.get("user_name") or "")
                if recipient_name == valid_user_name():
                    dm_key = dm_key_for(sender_name)
                    if dm_key not in dm_conversations:
                        dm_conversations[dm_key] = []
                    dm_conversations[dm_key].append(
                        Message(
                            user_name=sender_name,
                            text=message.get("text") or "",
                            message_type="direct_message",
                            room_name="",
                            message_id=message.get("message_id") or uuid.uuid4().hex,
                            tab_id=message.get("tab_id") or "",
                            recipient_name=recipient_name,
                            reaction_users={key: [] for key in REACTIONS},
                        )
                    )
                    persist_history()
                    if selected_dm_user != sender_name:
                        dm_unread_by_user[sender_name] = dm_unread_by_user.get(sender_name, 0) + 1
                    refresh_dm_sidebar()
                    if selected_dm_user == sender_name:
                        load_room_messages()
                    page.update()
                return
            
            if message_type == "room_created":
                verify_room(message_room)
                persist_history()
                page.update()
                return

            topic_name = normalize_room_name(topic_from_event or message_room or "geral")
            if topic_name not in room_history:
                room_history[topic_name] = []

            if message_type in ("chat_message", "login_message"):
                track_room_user(topic_name, str(message.get("user_name") or ""))

            if message_type == "presence_request":
                requester_name = str(message.get("user_name") or "")
                track_room_user(topic_name, requester_name)
                if requester_name and requester_name != (valid_user_name() or ""):
                    send_presence_announce(topic_name, requester_name)
                if topic_name == current_room:
                    refresh_users_sidebar()
                    page.update()
                return

            if message_type == "presence_announce":
                announced_user = str(message.get("user_name") or "")
                recipient_name = str(message.get("recipient_name") or "")
                current_user = valid_user_name() or ""
                if not recipient_name or recipient_name == current_user:
                    track_room_user(topic_name, announced_user)
                    if topic_name == current_room:
                        refresh_users_sidebar()
                        page.update()
                return

            if message_type == "reaction_update":
                target_message_id = str(message.get("target_message_id") or "")
                reaction_key = str(message.get("reaction_type") or "")
                reaction_action = str(message.get("reaction_action") or "add")
                reacting_tab_id = str(message.get("tab_id") or "")

                reaction_request_id = str(message.get("reaction_request_id") or "")
                if not reaction_request_id or reaction_request_id in processed_reaction_requests:
                    return
                processed_reaction_requests.add(reaction_request_id)

                updated = False
                for existing_message in room_history[topic_name]:
                    if existing_message.message_id == target_message_id:
                        apply_reaction_to_message(existing_message, reacting_tab_id, reaction_key, reaction_action)
                        updated = True
                        break

                if not updated:
                    updated = apply_reaction_to_dm_message(target_message_id, reacting_tab_id, reaction_key, reaction_action)

                if updated and topic_name == current_room:
                    load_room_messages()
                    page.update()
                return

            if message_type == "message_edit":
                target_message_id = str(message.get("target_message_id") or "")
                new_text = str(message.get("text") or "")
                target_message = find_message(topic_name, target_message_id)
                if target_message and can_manage(
                    str(message.get("user_name") or ""),
                    str(message.get("tab_id") or ""),
                    target_message,
                ):
                    target_message.text = new_text
                    target_message.edited = True
                    persist_history()
                else:
                    update_dm_message_text(target_message_id, new_text, deleted_for_all=False)
                if topic_name == current_room:
                    load_room_messages()
                    page.update()
                return

            if message_type == "message_delete_all":
                target_message_id = str(message.get("target_message_id") or "")
                target_message = find_message(topic_name, target_message_id)
                if target_message and can_manage(
                    str(message.get("user_name") or ""),
                    str(message.get("tab_id") or ""),
                    target_message,
                ):
                    target_message.text = "Esta mensagem foi apagada."
                    target_message.attachment_name = ""
                    target_message.attachment_mime = ""
                    target_message.attachment_data = ""
                    target_message.attachment_size = 0
                    target_message.edited = False
                    target_message.deleted_for_all = True
                    persist_history()
                else:
                    update_dm_message_text(target_message_id, "Esta mensagem foi apagada.", deleted_for_all=True)
                if topic_name == current_room:
                    load_room_messages()
                    page.update()
                return

            room_history[topic_name].append(
                Message(
                    user_name=str(message.get("user_name") or message.get("user") or "Unk"),
                    text=str(message.get("text") or ""),
                    message_type=message_type,
                    room_name=topic_name,
                    message_id=str(message.get("message_id") or uuid.uuid4().hex),
                    tab_id=str(message.get("tab_id") or ""),
                    target_message_id=str(message.get("target_message_id") or ""),
                    reaction_request_id=str(message.get("reaction_request_id") or ""),
                    reaction_type=str(message.get("reaction_type") or ""),
                    reaction_action=str(message.get("reaction_action") or ""),
                    reaction_users={k: list(v) for k, v in dict(message.get("reaction_users") or {}).items()},
                    attachment_name=str(message.get("attachment_name") or ""),
                    attachment_mime=str(message.get("attachment_mime") or ""),
                    attachment_data=str(message.get("attachment_data") or ""),
                    attachment_size=int(message.get("attachment_size") or 0),
                    edited=bool(message.get("edited") or False),
                    deleted_for_all=bool(message.get("deleted_for_all") or False),
                )
            )
            persist_history()

            if topic_name == current_room:
                last_msg = room_history[topic_name][-1]
                if not is_hidden(topic_name, last_msg.message_id):
                    chat.controls.append(message_control(last_msg))
                    scroll_chat_to_latest()
                    refresh_users_sidebar()
                    page.update()
            return

        message_room = getattr(message, "room_name", "")
        if message.message_type == "room_created":
            verify_room(message_room)
            persist_history()
            page.update()
            return

        if message.message_type == "direct_message":
            recipient_name = getattr(message, "recipient_name", "")
            if recipient_name == valid_user_name():
                dm_key = dm_key_for(message.user_name)
                if dm_key not in dm_conversations:
                    dm_conversations[dm_key] = []
                dm_conversations[dm_key].append(message)
                persist_history()
                if selected_dm_user != message.user_name:
                    dm_unread_by_user[message.user_name] = dm_unread_by_user.get(message.user_name, 0) + 1
                refresh_dm_sidebar()
                if selected_dm_user == message.user_name:
                    load_room_messages()
                page.update()
            return

        topic_name = normalize_room_name(topic_from_event or message_room or "geral")
        if topic_name not in room_history:
            room_history[topic_name] = []

        if message.message_type in ("chat_message", "login_message"):
            track_room_user(topic_name, message.user_name)

        if message.message_type == "presence_request":
            requester_name = message.user_name
            track_room_user(topic_name, requester_name)
            if requester_name and requester_name != (valid_user_name() or ""):
                send_presence_announce(topic_name, requester_name)
            if topic_name == current_room:
                refresh_users_sidebar()
                page.update()
            return

        if message.message_type == "presence_announce":
            recipient_name = getattr(message, "recipient_name", "")
            current_user = valid_user_name() or ""
            if not recipient_name or recipient_name == current_user:
                track_room_user(topic_name, message.user_name)
                if topic_name == current_room:
                    refresh_users_sidebar()
                    page.update()
            return

        if message.message_type == "reaction_update":
            if not message.reaction_request_id or message.reaction_request_id in processed_reaction_requests:
                return
            processed_reaction_requests.add(message.reaction_request_id)

            reaction_action = getattr(message, "reaction_action", "add")

            updated = False
            for existing_message in room_history[topic_name]:
                if existing_message.message_id == message.target_message_id:
                    apply_reaction_to_message(existing_message, message.tab_id, message.reaction_type, reaction_action)
                    updated = True
                    break

            if not updated:
                updated = apply_reaction_to_dm_message(message.target_message_id, message.tab_id, message.reaction_type, reaction_action)

            if updated and topic_name == current_room:
                load_room_messages()
                page.update()
            return

        if message.message_type == "message_edit":
            target_message = find_message(topic_name, message.target_message_id)
            if target_message and can_manage(message.user_name, message.tab_id, target_message):
                target_message.text = message.text
                target_message.edited = True
                persist_history()
            else:
                update_dm_message_text(message.target_message_id, message.text, deleted_for_all=False)
            if topic_name == current_room:
                load_room_messages()
                page.update()
            return

        if message.message_type == "message_delete_all":
            target_message = find_message(topic_name, message.target_message_id)
            if target_message and can_manage(message.user_name, message.tab_id, target_message):
                target_message.text = "Esta mensagem foi apagada."
                target_message.attachment_name = ""
                target_message.attachment_mime = ""
                target_message.attachment_data = ""
                target_message.attachment_size = 0
                target_message.edited = False
                target_message.deleted_for_all = True
                persist_history()
            else:
                update_dm_message_text(message.target_message_id, "Esta mensagem foi apagada.", deleted_for_all=True)
            if topic_name == current_room:
                load_room_messages()
                page.update()
            return

        if not getattr(message, "room_name", ""):
            message = Message(
                user_name=message.user_name,
                text=message.text,
                message_type=message.message_type,
                room_name=topic_name,
                message_id=message.message_id or uuid.uuid4().hex,
                tab_id=message.tab_id,
                target_message_id=message.target_message_id,
                reaction_request_id=message.reaction_request_id,
                reaction_type=message.reaction_type,
                reaction_action=message.reaction_action,
                reaction_users=message.reaction_users,
                attachment_name=message.attachment_name,
                attachment_mime=message.attachment_mime,
                attachment_data=message.attachment_data,
                attachment_size=message.attachment_size,
                edited=message.edited,
                deleted_for_all=message.deleted_for_all,
            )

        if message.message_type == "chat_message":
            ensure_reactions(message)

        room_history[topic_name].append(message)
        persist_history()

        if topic_name == current_room and not is_hidden(topic_name, message.message_id):
            chat.controls.append(message_control(message))
            scroll_chat_to_latest()
            refresh_users_sidebar()
            page.update()

    # Mensagens de chat
    chat = ft.ListView(
        expand=True,
        spacing=10,
        auto_scroll=True,
    )

    room_badge = ft.Text("Sala atual: (não selecionada)", size=11, color=ft.Colors.WHITE_70)
    rooms_col = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)
    dm_col = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)
    users_col = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)

    new_message = ft.TextField(
        hint_text="Escreva uma mensagem...",
        autofocus=True,
        shift_enter=True,
        min_lines=1,
        max_lines=5,
        filled=True,
        expand=True,
        on_submit=send_message_click,
    )

    def insert_emoji(emoji: str):
        new_message.value = f"{new_message.value or ''}{emoji}"
        page.update()

    welcome_dlg = ft.AlertDialog(
        open=False,
        modal=True,
        title=ft.Text("Entrar com Google"),
        content=ft.Column(
            [
                ft.Text("Autentica-te para usar a app."),
                login_feedback,
            ],
            width=360,
            tight=True,
        ),
        actions=[ft.TextButton("Continuar com Google", on_click=google_login_click)],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    create_room_name = ft.TextField(
        label="Nome da sala",
        hint_text="ex: projeto-mobile",
        on_submit=create_room_click,
    )
    create_room_dlg = ft.AlertDialog(
        open=False,
        modal=True,
        title=ft.Text("Criar sala"),
        content=ft.Column([create_room_name], width=300, tight=True),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: close_create_room_dlg()),
            ft.TextButton("Criar", on_click=create_room_click),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    emoji_picker_dlg = ft.AlertDialog(
        open=False,
        modal=False,
        title=ft.Text("Emojis"),
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.TextButton(emoji, on_click=lambda _e, value=emoji: insert_emoji(value))
                        for emoji in EMOJI_SHORTCUTS
                    ],
                    wrap=True,
                    spacing=4,
                )
            ],
            width=360,
            tight=True,
        ),
        actions=[ft.TextButton("Fechar", on_click=lambda _: close_dialog(emoji_picker_dlg))],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def close_create_room_dlg():
        close_dialog(create_room_dlg)

    def open_dm_dialog(user_name: str):
        nonlocal current_dm_user
        if user_name == valid_user_name():
            return
        current_dm_user = user_name
        dm_recipient_input.value = ""
        dm_title.value = f"Mensagem privada para {user_name}"
        open_dialog(dm_dlg)

    def close_dm_dlg():
        close_dialog(dm_dlg)

    async def send_dm_click(_):
        nonlocal selected_dm_user
        if not current_dm_user:
            return
        
        message_text = (dm_recipient_input.value or "").strip()
        if not message_text:
            return

        stored_user_name = valid_user_name()
        if not stored_user_name:
            return

        msg = Message(
            user_name=stored_user_name,
            text=message_text,
            message_type="direct_message",
            room_name="",
            message_id=uuid.uuid4().hex,
            tab_id=tab_id,
            recipient_name=current_dm_user,
            reaction_users={key: [] for key in REACTIONS},
        )
        
        # Guardar localmente no lado do remetente
        dm_key = dm_key_for(current_dm_user)
        if dm_key not in dm_conversations:
            dm_conversations[dm_key] = []
        dm_conversations[dm_key].append(msg)
        persist_history()
        
        # Enviar para o destinatário
        page.pubsub.send_all_on_topic(current_dm_user, msg)
        selected_dm_user = current_dm_user
        dm_unread_by_user[current_dm_user] = 0
        room_badge.value = f"Conversa privada: {current_dm_user}"
        new_message.hint_text = f"Mensagem privada para {current_dm_user}"
        load_room_messages()
        refresh_dm_sidebar()
        
        dm_recipient_input.value = ""
        close_dm_dlg()
        page.update()

    dm_title = ft.Text("Mensagem privada")
    dm_dlg = ft.AlertDialog(
        open=False,
        modal=False,
        title=dm_title,
        content=ft.Column([dm_recipient_input], width=350, tight=True),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda _: close_dm_dlg()),
            ft.TextButton("Enviar", on_click=send_dm_click),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.overlay.append(welcome_dlg)
    page.overlay.append(create_room_dlg)
    page.overlay.append(dm_dlg)
    page.overlay.append(emoji_picker_dlg)
    page.overlay.append(image_preview_dlg)
    page.overlay.append(message_actions_dlg)
    page.overlay.append(edit_message_dlg)
    file_picker = ft.FilePicker()
    page.services.append(file_picker)
    page.on_login = on_oauth_login
    page.on_connect = on_page_connect
    page.update()

    create_room_btn = ft.FilledButton(
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.ADD, size=16, color=ft.Colors.WHITE),
                ft.Text("Nova sala", color=ft.Colors.WHITE),
            ],
            tight=True,
            spacing=6,
        ),
        tooltip="Criar uma nova sala",
        on_click=open_create_room_dlg,
        disabled=True,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_500,
            color=ft.Colors.WHITE,
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            shape=ft.RoundedRectangleBorder(radius=10),
        ),
    )

    chat_background_image = ft.Image(
        src="",
        fit=ft.BoxFit.COVER,
        visible=False,
        width=0,
        height=0,
    )

    def sync_background_size(_=None):
        chat_background_image.width = max(1, int(page.width or 1))
        chat_background_image.height = max(1, int(page.height or 1))

    def apply_chat_background(path: str):
        nonlocal current_chat_background
        current_chat_background = (path or "").strip()
        sync_background_size()
        if current_chat_background:
            chat_background_image.src = (
                current_chat_background
                if current_chat_background.startswith("/")
                else f"/{current_chat_background}"
            )
        else:
            chat_background_image.src = ""
        chat_background_image.visible = bool(current_chat_background)
        page.update()

    def build_background_preview_option(path: str, label: str) -> ft.Control:
        preview: ft.Control
        if path:
            preview = ft.Image(src=f"/{path}", width=120, height=70, fit=ft.BoxFit.COVER)
        else:
            preview = ft.Container(
                width=120,
                height=70,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=8,
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.BLOCK, size=16, color=ft.Colors.WHITE_54),
                        ft.Text("Sem fundo", size=11, color=ft.Colors.WHITE_70),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=6,
                ),
            )

        return ft.Container(
            width=130,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=10,
            padding=6,
            on_click=lambda _e, value=path: apply_chat_background(value),
            content=ft.Column(
                controls=[
                    preview,
                    ft.Text(label, size=11, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ],
                spacing=6,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def get_glass_colors() -> tuple[str, str]:
        is_dark = page.theme_mode != ft.ThemeMode.LIGHT
        if is_dark:
            return (
                ft.Colors.with_opacity(0.42, ft.Colors.BLACK),
                ft.Colors.with_opacity(0.26, ft.Colors.BLACK),
            )
        return (
            ft.Colors.with_opacity(0.52, ft.Colors.WHITE),
            ft.Colors.with_opacity(0.36, ft.Colors.WHITE),
        )

    def update_theme_button_visual():
        is_dark = page.theme_mode != ft.ThemeMode.LIGHT
        theme_toggle_btn.icon = ft.Icons.LIGHT_MODE_OUTLINED if is_dark else ft.Icons.DARK_MODE_OUTLINED
        theme_toggle_btn.tooltip = "Tema claro" if is_dark else "Tema escuro"

    def apply_glass_theme_colors():
        panel_glass_bg, nested_glass_bg = get_glass_colors()
        rooms_nav_panel.bgcolor = nested_glass_bg
        dms_nav_panel.bgcolor = nested_glass_bg
        left_panel_shell.bgcolor = panel_glass_bg
        center_panel_shell.bgcolor = panel_glass_bg
        right_panel_shell.bgcolor = panel_glass_bg

    def set_mobile_panel(panel_name: str):
        nonlocal mobile_active_panel
        mobile_active_panel = panel_name if panel_name in {"rooms", "chat", "users"} else "chat"

        mobile_rooms_btn.style = ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_400 if mobile_active_panel == "rooms" else ft.Colors.GREY_800,
            color=ft.Colors.WHITE,
            padding=8,
        )
        mobile_chat_btn.style = ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_400 if mobile_active_panel == "chat" else ft.Colors.GREY_800,
            color=ft.Colors.WHITE,
            padding=8,
        )
        mobile_users_btn.style = ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_400 if mobile_active_panel == "users" else ft.Colors.GREY_800,
            color=ft.Colors.WHITE,
            padding=8,
        )

        mobile_panel_container.content = {
            "rooms": left_panel_shell,
            "chat": center_panel_shell,
            "users": right_panel_shell,
        }[mobile_active_panel]

    def update_layout_mode(width: float | None = None):
        nonlocal current_layout_mode
        current_width = float(width or page.width or 0)
        new_mode = "mobile" if current_width and current_width < MOBILE_LAYOUT_BREAKPOINT else "desktop"
        current_layout_mode = new_mode

        is_mobile = current_layout_mode == "mobile"
        desktop_layout.visible = not is_mobile
        mobile_layout.visible = is_mobile

        if is_mobile:
            left_panel_shell.width = None
            center_panel_shell.width = None
            right_panel_shell.width = None
            left_panel_shell.expand = False
            center_panel_shell.expand = True
            right_panel_shell.expand = False
            set_mobile_panel(mobile_active_panel)
        else:
            left_panel_shell.width = 260
            center_panel_shell.width = None
            right_panel_shell.width = 270
            left_panel_shell.expand = False
            center_panel_shell.expand = 5
            right_panel_shell.expand = False

        page.update()

    def toggle_theme(_):
        is_dark = page.theme_mode != ft.ThemeMode.LIGHT
        page.theme_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
        update_theme_button_visual()
        apply_glass_theme_colors()
        page.update()

    def logout_click(_):
        nonlocal active_user_name, login_bootstrapped, selected_dm_user

        user_to_remove = (active_user_name or valid_user_name() or "").strip()

        try:
            logout_result = page.logout()
            if asyncio.iscoroutine(logout_result):
                asyncio.create_task(logout_result)
        except Exception:
            pass

        active_user_name = ""
        login_bootstrapped = False
        selected_dm_user = ""
        page.session.store.set("user_name", "")
        page.run_task(clear_saved_auth_token)
        new_message.value = ""
        new_message.disabled = True
        create_room_btn.disabled = True
        room_badge.value = "Sala atual: sem sessão"
        if user_to_remove:
            for users_in_room in room_users_by_room.values():
                users_in_room.discard(user_to_remove)
        dm_unread_by_user.clear()
        refresh_users_sidebar()
        refresh_dm_sidebar()
        chat.controls.clear()
        close_dialog(settings_dlg)
        open_dialog(welcome_dlg)

    theme_toggle_btn = ft.IconButton(
        icon=ft.Icons.DARK_MODE_OUTLINED,
        tooltip="Alternar tema",
        on_click=toggle_theme,
    )
    settings_btn = ft.IconButton(
        icon=ft.Icons.SETTINGS_ROUNDED,
        tooltip="Definições",
        on_click=lambda _: open_dialog(settings_dlg),
    )

    settings_dlg = ft.AlertDialog(
        open=False,
        modal=True,
        title=ft.Text("Definições"),
        content=ft.Column(
            controls=[
                ft.Text("Imagem de fundo da conversa", weight=ft.FontWeight.W_600),
                ft.Row(
                    controls=[
                        build_background_preview_option(path, label)
                        for path, label in CHAT_BACKGROUND_PRESETS
                    ],
                    wrap=True,
                    spacing=6,
                ),
                ft.Divider(height=10),
                ft.TextButton("Terminar sessão", on_click=logout_click),
            ],
            width=430,
            tight=True,
        ),
        actions=[ft.TextButton("Fechar", on_click=lambda _: close_dialog(settings_dlg))],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.overlay.append(settings_dlg)
    update_theme_button_visual()
    sync_background_size()

    def bootstrap_session_state():
        nonlocal active_user_name
        stored_user_name = valid_user_name()
        if not stored_user_name:
            active_user_name = ""
            new_message.disabled = True
            create_room_btn.disabled = True
            if page.web:
                login_feedback.value = "A recuperar sessão..."
                open_dialog(welcome_dlg)
                page.run_task(recover_session_with_retry)
                return
            open_dialog(welcome_dlg)
            return

        active_user_name = stored_user_name
        new_message.disabled = False
        create_room_btn.disabled = False
        close_dialog(welcome_dlg)

        topic_subscription()
        ensure_private_subscription(stored_user_name)
        load_persisted_history()

        stored_room_name = page.session.store.get("room_name")
        if not isinstance(stored_room_name, str) or not stored_room_name.strip():
            stored_room_name = "geral"

        ensured_room = verify_room(stored_room_name)
        switch_room(ensured_room)

    bootstrap_session_state()

    panel_glass_bg, nested_glass_bg = get_glass_colors()

    # Adicionar tudo à página
    rooms_nav_panel = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Salas", weight=ft.FontWeight.BOLD, size=14),
                ft.Container(content=create_room_btn),
                rooms_col,
            ],
            spacing=6,
            expand=True,
        ),
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=5,
        padding=10,
        bgcolor=nested_glass_bg,
        width=260,
    )
    dms_nav_panel = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Mensagens privadas", weight=ft.FontWeight.BOLD, size=14),
                dm_col,
            ],
            spacing=6,
            expand=True,
        ),
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=5,
        padding=10,
        bgcolor=nested_glass_bg,
        width=260,
    )

    dm_tab_badge_text = ft.Text("0", size=10, color=ft.Colors.WHITE)
    dm_tab_badge = ft.Container(
        content=dm_tab_badge_text,
        bgcolor=ft.Colors.RED_500,
        border_radius=10,
        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        visible=False,
    )

    room_tab_btn = ft.TextButton("Salas", on_click=lambda _: show_left_nav("rooms"))
    dm_tab_btn = ft.TextButton(
        content=ft.Row(
            controls=[
                ft.Text("DMs"),
                dm_tab_badge,
            ],
            spacing=6,
            tight=True,
        ),
        on_click=lambda _: show_left_nav("dms"),
    )
    refresh_left_sidebar()

    left_panel_shell = ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        room_tab_btn,
                        dm_tab_btn,
                        ft.Container(content=room_badge, expand=True),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                rooms_nav_panel,
                dms_nav_panel,
            ],
            spacing=6,
            expand=True,
        ),
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=5,
        padding=10,
        bgcolor=panel_glass_bg,
        width=260,
    )

    center_panel_shell = ft.Container(
        content=ft.Column(
            controls=[
                chat,
                ft.Container(
                    content=ft.Row(
                        controls=[
                            new_message,
                            ft.IconButton(
                                icon=ft.Icons.EMOJI_EMOTIONS_OUTLINED,
                                tooltip="Inserir emoji",
                                on_click=lambda _: open_dialog(emoji_picker_dlg),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.IMAGE_OUTLINED,
                                tooltip="Anexar imagem",
                                on_click=send_image_attachment,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.ATTACH_FILE,
                                tooltip="Anexar ZIP",
                                on_click=send_zip_attachment,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.SEND_ROUNDED,
                                tooltip="Enviar mensagem",
                                on_click=send_message_click,
                            ),
                        ]
                    ),
                    padding=ft.Padding.only(top=8),
                ),
            ],
            expand=True,
            spacing=0,
        ),
        border=ft.Border.all(1, ft.Colors.OUTLINE),
        border_radius=5,
        padding=10,
        bgcolor=panel_glass_bg,
        expand=5,
    )

    right_panel_shell = ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("Utilizadores na sala", weight=ft.FontWeight.BOLD, size=14),
                        ft.Container(expand=True),
                        theme_toggle_btn,
                        settings_btn,
                    ],
                    spacing=2,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(height=8),
                users_col,
            ],
            spacing=6,
            expand=True,
        ),
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=5,
        padding=10,
        bgcolor=panel_glass_bg,
        width=270,
    )

    mobile_rooms_btn = ft.TextButton("Salas", on_click=lambda _: set_mobile_panel("rooms"))
    mobile_chat_btn = ft.TextButton("Chat", on_click=lambda _: set_mobile_panel("chat"))
    mobile_users_btn = ft.TextButton("Utilizadores", on_click=lambda _: set_mobile_panel("users"))
    mobile_nav_row = ft.Row(
        controls=[mobile_rooms_btn, mobile_chat_btn, mobile_users_btn],
        spacing=6,
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )
    mobile_panel_container = ft.Container(expand=True)

    desktop_layout = ft.Column(
        controls=[
            ft.Row(
                controls=[
                    ft.Text("DiscirdApp", size=30, weight=ft.FontWeight.BOLD),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                controls=[
                    left_panel_shell,
                    center_panel_shell,
                    right_panel_shell,
                ],
                expand=True,
                spacing=10,
            ),
        ],
        expand=True,
    )

    mobile_layout = ft.Column(
        controls=[
            ft.Row(
                controls=[
                    ft.Text("DiscirdApp", size=24, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    theme_toggle_btn,
                    settings_btn,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            room_badge,
            mobile_nav_row,
            mobile_panel_container,
        ],
        spacing=10,
        expand=True,
        visible=False,
    )

    apply_glass_theme_colors()

    page.add(
        ft.Stack(
            controls=[
                chat_background_image,
                desktop_layout,
                mobile_layout,
            ],
            expand=True,
        )
    )

    page.on_resize = lambda e: (sync_background_size(e), update_layout_mode(getattr(e, "width", None)))
    update_layout_mode(page.width)


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "60123"))
    os.environ.setdefault("FLET_SESSION_TIMEOUT", "86400")

    # For cloud deploys (Fly.io/Replit), set HOST=0.0.0.0 and PORT via env.
    ft.run(
        main=main,
        view=ft.AppView.WEB_BROWSER,
        host=host,
        port=port,
        assets_dir="assets",
    )