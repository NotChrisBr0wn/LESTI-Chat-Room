from dataclasses import dataclass, field
import uuid

import flet as ft


@dataclass
class Message:  # noqa: B903
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


REACTIONS = {
    "laugh": "😂",
    "cry": "😢",
    "heart": "❤️",
    "cool": "👍",
}

@ft.control
class ChatMessage(ft.Row):
    def __init__(self, message: Message, on_react):
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

        self.controls = [
            ft.CircleAvatar(
                content=ft.Text(self.get_initials(self.message.user_name)),
                color=ft.Colors.WHITE,
                bgcolor=self.get_avatar_color(self.message.user_name),
            ),
            ft.Column(
                tight=True,
                spacing=5,
                controls=[
                    ft.Text(
                        self.message.user_name,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.GREEN_800,
                    ),
                    ft.Text(self.message.text, selectable=True, color=ft.Colors.WHITE_70),
                    ft.Row(controls=reaction_buttons, spacing=4, wrap=True),
                ],
            ),
        ]

    def get_initials(self, user_name: str):
        if user_name:
            return user_name[:1].capitalize()
        else:
            return "Unk"  # Retorna "Unk" para nomes vazios ou nulos

    def get_avatar_color(self, user_name: str):
        colors_lookup = [
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
        return colors_lookup[hash(user_name) % len(colors_lookup)]

# Função principal 
def main(page: ft.Page):
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "Flet Chat"

    # Variáveis de estado
    topic = "__rooms__"
    rooms: list[str] = []
    subscribed_rooms: set[str] = set()
    room_history: dict[str, list[Message]] = {}
    processed_reaction_requests: set[str] = set()
    current_room = ""
    active_user_name = ""
    topic_subscribed = False
    tab_id = uuid.uuid4().hex

    # Funções auxiliares
    def open_dialog(dialog: ft.AlertDialog):
        dialog.open = True
        page.update()
        
    def close_dialog(dialog: ft.AlertDialog):
        dialog.open = False
        page.update()
    
    # Valida o nome de utilizador atraves do armazenamento da sessão, garantindo que é uma string não vazia    
    def valid_user_name() -> str:
        if active_user_name:
            return active_user_name

        stored_user_name = page.session.store.get("user_name")
        if isinstance(stored_user_name, str):
            user_name = stored_user_name.strip()
            if user_name:
                return user_name
        return ""

    def is_logged_in() -> bool:
        return bool(valid_user_name())
    
    # Normaliza o nome da sala para garantir consistência (removendo espaços e convertendo em minusculas)
    def normalize_room_name(value: str) -> str:
        return (value or "").strip().lower()

    def ensure_reactions(message: Message):
        for reaction_key in REACTIONS:
            if reaction_key not in message.reaction_users:
                message.reaction_users[reaction_key] = []

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

        if reacting_tab_id in users:
            users.remove(reacting_tab_id)
        return True

    def react(target_message_id: str, reaction_key: str):
        if not target_message_id or reaction_key not in REACTIONS:
            return

        stored_user_name = valid_user_name() or "Unk"
        stored_room_name = page.session.store.get("room_name")
        if not isinstance(stored_room_name, str) or not stored_room_name:
            return

        reaction_action = "add"
        for existing_message in room_history.get(stored_room_name, []):
            if existing_message.message_id == target_message_id:
                ensure_reactions(existing_message)
                current_users = existing_message.reaction_users.get(reaction_key, [])
                reaction_action = "remove" if tab_id in current_users else "add"
                break

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

    # Controlo de mensagem (formatação diferente para mensagens de chat e de sistema)
    def message_control(message: Message):
        if message.message_type == "chat_message":
            ensure_reactions(message)
            return ChatMessage(message, on_react=react)
        return ft.Text(
            message.text,
            style=ft.TextStyle(italic=True),
            color=ft.Colors.BLUE_700,
            size=12,
        )
        
    # Atualiza a lista de mensagens da sala atual
    def load_room_messages():
        chat.controls.clear()
        for message in room_history.get(current_room, []):
            chat.controls.append(message_control(message))

    def update_rooms():
        tab_controls: list[ft.Control] = [
            ft.TextButton(
                content=ft.Text(room_name),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_200 if room_name == current_room else ft.Colors.GREY_300,
                    color=ft.Colors.BLACK,
                ),
                on_click=lambda e, selected_room=room_name: switch_room(selected_room),
            )
            for room_name in rooms
        ]
        room_tabs_row.controls = tab_controls

    # Garante que o utilizador esteja subscrito ao topico principal
    def topic_subscription():
        nonlocal topic_subscribed
        if topic_subscribed:
            return

        page.pubsub.subscribe_topic(topic, on_message)
        topic_subscribed = True

    # Verifica se a sala existe e se nao cria e subscreve o utilizador
    def verify_room(room_name: str):
        room = normalize_room_name(room_name)
        if not room:
            return ""

        if room not in rooms:
            rooms.append(room)

        if room not in subscribed_rooms:
            page.pubsub.subscribe_topic(room, on_message)
            subscribed_rooms.add(room)

        if room not in room_history:
            room_history[room] = []

        update_rooms()
        return room

    def switch_room(room_name: str):
        nonlocal current_room
        room = verify_room(room_name)
        if not room:
            return

        current_room = room
        page.session.store.set("room_name", current_room)
        room_badge.value = f"Sala atual: {current_room}"

        stored_user_name = valid_user_name() or "Unk"
        new_message.hint_text = f"Mensagem para {stored_user_name}@{current_room}"

        load_room_messages()
        update_rooms()

    def join_chat_click(e):
        nonlocal active_user_name
        user_name = (join_name.value or "").strip()
        if not user_name:
            join_name.error = "O nome não pode estar vazio."
            page.update()
            return

        join_name.error = None
        active_user_name = user_name
        page.session.store.set("user_name", user_name)
        close_dialog(welcome_dlg)

        topic_subscription()
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
        page.update()

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

    # Função para lidar com o envio de mensagens
    async def send_message_click(e):
        message_text = (new_message.value or "").strip()
        if not message_text:
            return

        stored_user_name = valid_user_name()
        if not stored_user_name:
            join_name.error = "Inicia sessão para enviar mensagens."
            open_dialog(welcome_dlg)
            return

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
            if message_type == "room_created":
                verify_room(message_room)
                page.update()
                return

            topic_name = normalize_room_name(topic_from_event or message_room or "geral")
            if topic_name not in room_history:
                room_history[topic_name] = []

            if message_type == "reaction_update":
                target_message_id = str(message.get("target_message_id") or "")
                reaction_key = str(message.get("reaction_type") or "")
                reaction_action = str(message.get("reaction_action") or "add")
                reacting_tab_id = str(message.get("tab_id") or "")

                reaction_request_id = str(message.get("reaction_request_id") or "")
                if not reaction_request_id or reaction_request_id in processed_reaction_requests:
                    return
                processed_reaction_requests.add(reaction_request_id)

                for existing_message in room_history[topic_name]:
                    if existing_message.message_id == target_message_id:
                        if reaction_action == "remove":
                            remove_reaction(existing_message, reacting_tab_id, reaction_key)
                        else:
                            add_reaction(existing_message, reacting_tab_id, reaction_key)
                        break

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
                    reaction_request_id=str(message.get("reaction_request_id") or ""),
                    reaction_type=str(message.get("reaction_type") or ""),
                    reaction_users={k: list(v) for k, v in dict(message.get("reaction_users") or {}).items()},
                )
            )

            if topic_name == current_room:
                last_msg = room_history[topic_name][-1]
                chat.controls.append(message_control(last_msg))
                page.update()
            return

        message_room = getattr(message, "room_name", "")
        if message.message_type == "room_created":
            verify_room(message_room)
            page.update()
            return

        topic_name = normalize_room_name(topic_from_event or message_room or "geral")
        if topic_name not in room_history:
            room_history[topic_name] = []

        if message.message_type == "reaction_update":
            if not message.reaction_request_id or message.reaction_request_id in processed_reaction_requests:
                return
            processed_reaction_requests.add(message.reaction_request_id)

            reaction_action = getattr(message, "reaction_action", "add")

            for existing_message in room_history[topic_name]:
                if existing_message.message_id == message.target_message_id:
                    if reaction_action == "remove":
                        remove_reaction(existing_message, message.tab_id, message.reaction_type)
                    else:
                        add_reaction(existing_message, message.tab_id, message.reaction_type)
                    break

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
                reaction_request_id=message.reaction_request_id,
                reaction_type=message.reaction_type,
                reaction_users=message.reaction_users,
            )

        if message.message_type == "chat_message":
            ensure_reactions(message)

        room_history[topic_name].append(message)

        if topic_name == current_room:
            chat.controls.append(message_control(message))
            page.update()

    # Mensagens de chat
    chat = ft.ListView(
        expand=True,
        spacing=10,
        auto_scroll=True,
    )

    room_badge = ft.Text("Sala atual: (não selecionada)", size=12, color=ft.Colors.WHITE_70)
    room_tabs_row = ft.Row(wrap=True, spacing=8)

    # Novo formulário de mensagem
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

    # Caixa de dialogo que pede o nome de utilizador
    join_name = ft.TextField(
        label="Introduza o seu nome",
        autofocus=True,
        on_submit=join_chat_click,
    )

    welcome_dlg = ft.AlertDialog(
        open=False,
        modal=True,
        title=ft.Text("Bem-vindo a LESTI chat room!"),
        content=ft.Column([join_name], width=300, tight=True),
        actions=[ft.Button(content="Entrar", on_click=join_chat_click)],
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
            ft.Button(content="Criar", on_click=create_room_click),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def close_create_room_dlg():
        close_dialog(create_room_dlg)

    page.overlay.append(welcome_dlg)
    page.overlay.append(create_room_dlg)

    create_room_btn = ft.IconButton(
        icon=ft.Icons.ADD_BOX_ROUNDED,
        tooltip="+",
        on_click=open_create_room_dlg,
        disabled=True,
    )

    def bootstrap_session_state():
        nonlocal active_user_name
        stored_user_name = valid_user_name()
        if not stored_user_name:
            active_user_name = ""
            new_message.disabled = True
            create_room_btn.disabled = True
            open_dialog(welcome_dlg)
            return

        active_user_name = stored_user_name
        new_message.disabled = False
        create_room_btn.disabled = False
        close_dialog(welcome_dlg)

        stored_room_name = page.session.store.get("room_name")
        if not isinstance(stored_room_name, str) or not stored_room_name.strip():
            stored_room_name = "geral"

        ensured_room = verify_room(stored_room_name)
        switch_room(ensured_room)

    bootstrap_session_state()

    # Adicionar tudo à página
    page.add(
        ft.Row(
            controls=[
                create_room_btn,
                room_tabs_row,
            ],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        room_badge,
        ft.Container(
            content=chat,
            border=ft.Border.all(1, ft.Colors.OUTLINE),
            border_radius=5,
            padding=10,
            expand=True,
        ),
        ft.Row(
            controls=[
                new_message,
                ft.IconButton(
                    icon=ft.Icons.SEND_ROUNDED,
                    tooltip="Enviar mensagem",
                    on_click=send_message_click,
                ),
            ]
        ),
    )


ft.run(main)