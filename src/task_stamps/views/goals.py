"""Goals: numeric targets walked by a character along a ten-section track."""

from __future__ import annotations

from datetime import date

import flet as ft

from task_stamps.components.common import confirm_dialog, goal_image, goal_track
from task_stamps.components.theme import (
    ACCENT, BAD, BG_2, BG_HOVER_ALPHA, FAINT, MUTED, MUTED_2, SERIF, TEXT, TEXT_DIM,
    eyebrow, eyebrow_row, hairline, style_dialog, text_action,
)
from task_stamps.domain import goal_track as track
from task_stamps.domain.enums import (
    GOAL_SECTIONS, GoalEntryOutcome, GoalLegEndReason, GoalStatus, PoolType,
)
from task_stamps.domain.exceptions import TaskStampsError
from task_stamps.domain.models import Goal
from task_stamps.services.goal_service import GoalView, ProgressResult
from task_stamps.views.base import View

_GROUPS = (
    (GoalStatus.REACHED, "Reached — your call"),
    (GoalStatus.ACTIVE, "Under way"),
    (GoalStatus.FINISHED, "Finished"),
)


def _amount(goal: Goal, value: float) -> str:
    return f"{track.format_value(value)} {goal.unit}".strip()


def _signed(value: float) -> str:
    return ("+" if value > 0 else "−" if value < 0 else "±") + track.format_value(abs(value))


def _parse_number(text: str | None) -> float:
    """Accept '+3', '-2', '−2' and '3,5' as well as plain numbers."""
    cleaned = (text or "").strip().replace("−", "-").replace(",", ".").replace(" ", "")
    return float(cleaned)


def _field(label: str, value: str = "", **extra) -> ft.TextField:
    return ft.TextField(label=label, value=value, border=ft.InputBorder.UNDERLINE, **extra)


def _review_phrase(next_review: date, today: date) -> str:
    days = (next_review - today).days
    if days < 0:
        return f"Review overdue by {-days} day{'s' if days != -1 else ''}"
    if days == 0:
        return "Review due today"
    if days == 1:
        return "Next review tomorrow"
    return f"Next review {next_review.strftime('%a %d %b')}"


class GoalsView(View):
    def build(self) -> ft.Control:
        self.summary = ft.Text()
        self.rows = ft.Column(spacing=0)
        header = ft.Row([
            ft.Column([
                eyebrow("Pursuits"),
                ft.Text("Goals", size=48, color=TEXT, font_family=SERIF,
                        style=ft.TextStyle(height=1.04)),
                self.summary,
            ], spacing=10, expand=True),
            text_action("Set a goal →", lambda _: self.open_editor(None), size=14),
        ], vertical_alignment=ft.CrossAxisAlignment.END)
        return ft.Container(
            content=ft.Column([
                header,
                self.rows,
                ft.Text("Each goal is cut into ten sections and carried by one character, whose "
                        "ranked image changes as you cross each 10%. Slip past where you started "
                        "and someone new takes over from there. Reach the end and a chest drops "
                        "for the reward you picked. Log an entry at least once a week — logging "
                        "no change still counts as the review.",
                        size=13, color=MUTED_2, width=580),
            ], spacing=32, scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.only(left=56, right=56, top=40, bottom=72),
            expand=True,
        )

    # -- list ---------------------------------------------------------------

    def refresh(self) -> None:
        service = self.app.container.goal_service
        service.assign_waiting_characters()
        views = service.views()
        due = sum(1 for view in views if view.review_due)
        running = sum(1 for view in views if view.goal.status != GoalStatus.FINISHED)
        if not views:
            self.summary.spans = [ft.TextSpan(
                "Numbers you are walking toward, one section at a time.",
                ft.TextStyle(size=15, color=TEXT_DIM))]
        else:
            self.summary.spans = [
                ft.TextSpan(str(due), ft.TextStyle(font_family=SERIF, size=26,
                                                   color=ACCENT if due else MUTED_2)),
                ft.TextSpan(f" review{'' if due == 1 else 's'} due across {running} "
                            f"goal{'' if running == 1 else 's'} in play.",
                            ft.TextStyle(size=15, color=TEXT_DIM)),
            ]
        controls: list[ft.Control] = []
        for status, label in _GROUPS:
            group = [view for view in views if view.goal.status == status]
            if status == GoalStatus.ACTIVE:
                group.sort(key=lambda v: (not v.review_due, v.next_review_on or date.max))
            if not group:
                continue
            controls.append(ft.Container(height=6))
            controls.append(eyebrow_row(label))
            for view in group:
                controls.extend([self._row(view), hairline()])
        if not controls:
            controls = [self._empty()]
        self.rows.controls = controls
        self.app.refresh_goal_count()
        self.page.update()

    def _empty(self) -> ft.Control:
        ready = self.app.container.characters.goal_eligible_character_ids(PoolType.ALL_WORLDS, None)
        note = (
            f"{len(ready)} character{'s are' if len(ready) != 1 else ' is'} free to carry one."
            if ready else
            "No character has all ten goal images yet — add them in a character's profile "
            "under Worlds, or publish them from World Hub."
        )
        return ft.Column([
            ft.Text("Nothing on the path yet", size=33, color=TEXT, font_family=SERIF),
            ft.Text("Pick a number to move toward — pages read, kilos lost, savings put by — "
                    "and a character will walk it with you.", size=15, color=TEXT_DIM),
            ft.Text(note, size=13, color=MUTED),
        ], spacing=10)

    def _row(self, view: GoalView) -> ft.Control:
        goal = view.goal
        today = self.app.container.clock.today()
        carrier = view.character.name if view.character else "no one yet"
        finished = goal.status == GoalStatus.FINISHED
        if goal.status == GoalStatus.ACTIVE:
            detail = (f"held by {carrier} · {_amount(goal, goal.baseline_value)} → "
                      f"{_amount(goal, goal.target_value)} · now {_amount(goal, goal.current_value)}")
            assert view.next_review_on is not None
            status_text = _review_phrase(view.next_review_on, today)
            status_color = ACCENT if view.review_due else MUTED_2
            action: ft.Control = text_action(
                "Log progress →", lambda _, g=goal.id: self.open_log(g),
                color=ACCENT if view.review_due else TEXT)
        elif goal.status == GoalStatus.REACHED:
            detail = f"{carrier} reached {_amount(goal, goal.target_value)}"
            status_text = "Extend the path or finish it."
            status_color = ACCENT
            action = text_action("Decide →", lambda _, v=view: self._show_reached(v), color=ACCENT)
        else:
            detail = f"carried home by {carrier} · {_amount(goal, goal.current_value)}"
            status_text = (f"Finished {goal.finished_at.strftime('%d %b %Y')}"
                           if goal.finished_at else "Finished")
            status_color = MUTED_2
            action = ft.Container()

        info = ft.Column([
            ft.Text(goal.name, size=25, color=TEXT_DIM if finished else TEXT, font_family=SERIF),
            ft.Text(detail, size=13.5, color=MUTED if finished else TEXT_DIM),
            ft.Text(spans=[
                ft.TextSpan(status_text, ft.TextStyle(size=13, color=status_color)),
                *([ft.TextSpan(f" · at the end: {view.reward_name}",
                               ft.TextStyle(size=13, color=MUTED_2))]
                  if goal.status == GoalStatus.ACTIVE and view.reward_name else []),
            ]),
        ], spacing=5, expand=True)
        right = ft.Column([
            ft.Text(spans=[
                ft.TextSpan(str(view.section), ft.TextStyle(font_family=SERIF, size=22, color=TEXT)),
                ft.TextSpan(f" / {GOAL_SECTIONS}", ft.TextStyle(font_family=SERIF, size=22, color=FAINT)),
            ], text_align=ft.TextAlign.RIGHT),
            goal_track(view.section, reached=goal.status != GoalStatus.ACTIVE),
            action,
        ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.END, width=168)
        row = ft.Container(
            padding=ft.padding.symmetric(vertical=22),
            ink=True,
            on_click=lambda _, g=goal.id: self.open_detail(g),
            opacity=0.72 if finished else 1.0,
            content=ft.Row([
                goal_image(self.app.img_src(view.image_version_id), width=76),
                info,
                right,
            ], spacing=26, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )
        row.on_hover = lambda e: setattr(
            e.control, "bgcolor", BG_HOVER_ALPHA if e.data == "true" else None
        ) or e.control.update()
        return row

    # -- detail -------------------------------------------------------------

    def open_detail(self, goal_id: str) -> None:
        service = self.app.container.goal_service
        view = service.view(goal_id)
        goal = view.goal
        today = self.app.container.clock.today()
        legs, entries = service.history(goal_id)
        running = goal.status == GoalStatus.ACTIVE

        figures = ft.Row([
            ft.Column([eyebrow(label), ft.Text(_amount(goal, value), size=30,
                                               color=color, font_family=SERIF, no_wrap=True)],
                      spacing=2)
            for label, value, color in (
                ("Start", goal.baseline_value, TEXT_DIM),
                ("Now", goal.current_value, TEXT),
                ("Goal", goal.target_value, ACCENT if goal.status == GoalStatus.REACHED else TEXT_DIM),
            )
        ], spacing=40)

        percent = round(view.fraction * 100)
        place = (
            f"Section {view.section} of {GOAL_SECTIONS} · {percent}% of the way"
            if running else "The whole track is walked."
        )

        ranks: list[ft.Control] = []
        for rank in range(1, GOAL_SECTIONS + 1):
            current = rank == view.section
            passed = rank < view.section or not running
            ranks.append(ft.Column([
                ft.Container(
                    content=goal_image(self.app.img_src(view.goal_images.get(rank)), 42, glow=False),
                    opacity=1.0 if passed or current else 0.28,
                ),
                ft.Container(width=18, height=2, bgcolor=ACCENT if current and running else None),
            ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER))

        entry_rows: list[ft.Control] = []
        for entry in entries[:8]:
            note = {
                GoalEntryOutcome.REACHED: " · reached the goal",
                GoalEntryOutcome.REBASED: " · slipped past the start",
            }.get(entry.outcome, "")
            entry_rows.append(ft.Text(
                f"{entry.entered_on.strftime('%a %d %b')}   {_signed(entry.delta)}  →  "
                f"{_amount(goal, entry.value_after)}{note}",
                size=13, color=TEXT_DIM if entry.outcome is GoalEntryOutcome.PROGRESS else MUTED))
        if not entry_rows:
            entry_rows.append(ft.Text("Nothing logged yet.", size=13, color=MUTED))

        path_rows: list[ft.Control] = []
        for leg in legs:
            name = (self.app.container.characters.get(leg.character_id).name
                    if leg.character_id else "Waiting for a character")
            span = f"{_amount(goal, leg.baseline_value)} → {_amount(goal, leg.target_value)}"
            if leg.is_active:
                outcome = "walking it now" if running else "reached it"
            elif leg.end_reason == GoalLegEndReason.REBASED:
                outcome = f"handed on at {_amount(goal, leg.end_value or 0)}"
            elif leg.end_reason == GoalLegEndReason.REACHED:
                outcome = "reached it"
            else:
                outcome = "set aside"
            path_rows.append(ft.Text(f"{leg.ordinal}.  {name} · {span} · {outcome}",
                                     size=13, color=TEXT_DIM if leg.is_active else MUTED))

        lines: list[ft.Control] = []
        if goal.description:
            lines.append(ft.Text(goal.description, size=14, color=TEXT_DIM))
        if view.reward_name:
            lines.append(ft.Text(f"At the end: {view.reward_name}", size=14, color=TEXT_DIM))
        if view.next_review_on:
            lines.append(ft.Text(_review_phrase(view.next_review_on, today), size=14,
                                 color=ACCENT if view.review_due else MUTED))

        details = ft.Column([
            eyebrow({GoalStatus.ACTIVE: "Under way", GoalStatus.REACHED: "Reached",
                     GoalStatus.FINISHED: "Finished"}.get(goal.status, "")),
            figures,
            ft.Container(height=4),
            goal_track(view.section, reached=not running, width=34),
            ft.Text(place, size=13, color=MUTED),
            *lines,
            ft.Container(height=6),
            eyebrow("Ranks"),
            ft.Row(ranks, spacing=6),
            ft.Container(height=6),
            eyebrow("Recent entries"),
            *entry_rows,
            ft.Container(height=6),
            eyebrow("The path"),
            *path_rows,
        ], spacing=10, scroll=ft.ScrollMode.AUTO, width=540, height=560)

        carrier = ft.Column([
            goal_image(self.app.img_src(view.image_version_id), width=380),
            ft.Text(view.character.name if view.character else "Waiting for a character",
                    size=24, color=TEXT, font_family=SERIF),
            ft.Text(f"Rank {view.section} of {GOAL_SECTIONS}", size=13, color=MUTED),
        ], spacing=6, width=380)

        dialog = style_dialog(ft.AlertDialog(
            title=ft.Text(goal.name),
            content=ft.Row([carrier, details], spacing=30, height=560,
                           vertical_alignment=ft.CrossAxisAlignment.START),
        ))

        def then(action) -> None:
            self.app.close_dialog(dialog)
            action()

        actions: list[ft.Control] = [
            ft.TextButton("Close", on_click=lambda _: self.app.close_dialog(dialog)),
        ]
        if service.undoable_entry(goal_id) is not None:
            actions.append(ft.TextButton(
                "Undo last entry", on_click=lambda _: then(lambda: self._undo(goal_id))))
        if goal.status in (GoalStatus.ACTIVE, GoalStatus.REACHED):
            actions.append(ft.TextButton(
                "Edit", on_click=lambda _: then(lambda: self.open_editor(goal_id))))
        actions.append(ft.TextButton(
            "Remove", style=ft.ButtonStyle(color=BAD),
            on_click=lambda _: then(lambda: self._confirm_remove(goal))))
        if running:
            actions.append(ft.TextButton(
                "Log progress", on_click=lambda _: then(lambda: self.open_log(goal_id))))
        elif goal.status == GoalStatus.REACHED:
            actions.append(ft.TextButton(
                "Decide", on_click=lambda _: then(lambda: self._show_reached(view))))
        dialog.actions = actions
        self.app.open_dialog(dialog)

    # -- editor -------------------------------------------------------------

    def _reward_options(self) -> list[ft.dropdown.Option]:
        return [
            ft.dropdown.Option(reward.id, f"{reward.name} — {reward.task_weight.value.title()} · "
                                          f"streak {reward.tier}")
            for reward in self.app.container.chests.list_rewards()
        ]

    def open_editor(self, goal_id: str | None) -> None:
        container = self.app.container
        goal = container.goals.get(goal_id) if goal_id else None
        name = _field("Name", goal.name if goal else "", width=420, autofocus=True)
        description = _field("Description (optional)", goal.description if goal else "",
                             width=420, multiline=True, min_lines=1)
        unit = _field("Unit (optional)", goal.unit if goal else "", width=130,
                      hint_text="kg, pages…")
        start = _field("Start", track.format_value(goal.baseline_value) if goal else "",
                       width=130, keyboard_type=ft.KeyboardType.NUMBER,
                       disabled=goal is not None)
        target = _field("Goal", track.format_value(goal.target_value) if goal else "",
                        width=130, keyboard_type=ft.KeyboardType.NUMBER,
                        disabled=goal is not None and goal.status == GoalStatus.REACHED)
        rewards = self._reward_options()
        reward = ft.Dropdown(
            label="Reward waiting at the end", width=420, border=ft.InputBorder.UNDERLINE,
            value=goal.reward_id if goal else (rewards[0].key if len(rewards) == 1 else None),
            options=rewards,
        )
        pool = ft.Dropdown(
            label="Characters from", width=420, border=ft.InputBorder.UNDERLINE,
            value=goal.world_id if goal and goal.pool_type == PoolType.SPECIFIC_WORLD else "all",
            options=[ft.dropdown.Option("all", "All worlds")]
            + [ft.dropdown.Option(world.id, world.name) for world in container.worlds.list()],
        )
        notes: list[ft.Control] = []
        if not rewards:
            notes.append(ft.Text("No rewards yet — add one on the Vice Chests screen first.",
                                 size=12.5, color=BAD))
        if goal is not None:
            notes.append(ft.Text(
                "The start moves on its own when you slip past it or extend the path. "
                "The goal can move further along the same direction.",
                size=12.5, color=MUTED_2))
        else:
            notes.append(ft.Text("Going down counts too: start at 90, aim for 80.",
                                 size=12.5, color=MUTED_2))
        dialog = style_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Edit goal" if goal else "Set a goal"),
            content=ft.Column([
                name, description,
                ft.Row([start, target, unit], spacing=16),
                reward, pool, *notes,
            ], tight=True, spacing=14, width=440),
        ))

        def save(_=None) -> None:
            pool_type = PoolType.ALL_WORLDS if (pool.value or "all") == "all" else PoolType.SPECIFIC_WORLD
            world_id = None if pool_type == PoolType.ALL_WORLDS else pool.value
            try:
                target_value = _parse_number(target.value)
                start_value = _parse_number(start.value) if goal is None else goal.baseline_value
            except ValueError:
                self.app.error(ValueError("Start and goal have to be numbers."))
                return
            try:
                if goal is None:
                    view = container.goal_service.create_goal(
                        name=name.value or "", description=description.value or "",
                        unit=unit.value or "", start_value=start_value,
                        target_value=target_value, reward_id=reward.value,
                        pool_type=pool_type, world_id=world_id,
                    )
                else:
                    view = container.goal_service.edit_goal(
                        goal.id, name=name.value or "", description=description.value or "",
                        unit=unit.value or "", target_value=target_value,
                        reward_id=reward.value, pool_type=pool_type, world_id=world_id,
                    )
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.app.close_dialog(dialog)
            self.refresh()
            if goal is None:
                self._show_carrier(view, "A character takes up the path",
                                   f"will walk '{view.goal.name}' with you, one section at a time.")
            else:
                self.app.notify("Goal saved.")

        dialog.actions = [
            ft.TextButton("Cancel", on_click=lambda _: self.app.close_dialog(dialog)),
            ft.TextButton("Save" if goal else "Set goal", on_click=save),
        ]
        self.app.open_dialog(dialog)

    # -- logging ------------------------------------------------------------

    def open_log(self, goal_id: str) -> None:
        service = self.app.container.goal_service
        view = service.view(goal_id)
        goal = view.goal
        preview = ft.Text(" ", size=13.5, color=MUTED)

        def update_preview(_=None) -> None:
            try:
                delta = _parse_number(change.value)
            except ValueError:
                preview.value, preview.color = "Type how much it moved, e.g. +3 or −2.", MUTED
                preview.update()
                return
            after = goal.current_value + delta
            if track.is_reached(goal.baseline_value, goal.target_value, after):
                preview.value = (f"→ {_amount(goal, after)} · that reaches the goal"
                                 + (f" — a chest drops for {view.reward_name}."
                                    if view.reward_name else "."))
                preview.color = ACCENT
            elif track.is_behind_baseline(goal.baseline_value, goal.target_value, after):
                preview.value = (f"→ {_amount(goal, after)} · past where this track starts. "
                                 "A new character takes over from there.")
                preview.color = BAD
            else:
                section = track.section(goal.baseline_value, goal.target_value, after)
                preview.value = f"→ {_amount(goal, after)} · section {section} of {GOAL_SECTIONS}"
                preview.color = TEXT_DIM
            preview.update()

        # Entries move the number itself, so "away from the goal" is a minus
        # sign on a goal that climbs and a plus sign on one that comes down.
        hint = (
            "Moved away from the goal? Use a minus sign."
            if goal.target_value > goal.baseline_value else
            "This goal comes down: a drop is −, a rise is +."
        ) + " Logging 0 still counts as this week's review."
        change = _field("Change", width=200, autofocus=True, hint_text="+3 or −2",
                        keyboard_type=ft.KeyboardType.NUMBER, on_change=update_preview)
        dialog = style_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text(goal.name),
            content=ft.Column([
                eyebrow("Now"),
                ft.Text(_amount(goal, goal.current_value), size=40, color=TEXT, font_family=SERIF),
                ft.Row([goal_track(view.section, width=22)]),
                ft.Container(height=4),
                change,
                preview,
                ft.Text(hint, size=12.5, color=MUTED_2),
            ], tight=True, spacing=8, width=420),
        ))

        def log(_=None) -> None:
            try:
                delta = _parse_number(change.value)
            except ValueError:
                self.app.error(ValueError("The change has to be a number, like +3 or −2."))
                return
            try:
                result = service.log_progress(goal_id, delta)
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.app.close_dialog(dialog)
            self.app.refresh_chest_count()
            self.refresh()
            self._announce(goal_id, result)

        change.on_submit = log
        dialog.actions = [
            ft.TextButton("Cancel", on_click=lambda _: self.app.close_dialog(dialog)),
            ft.TextButton("Log", on_click=log),
        ]
        self.app.open_dialog(dialog)

    def _announce(self, goal_id: str, result: ProgressResult) -> None:
        view = self.app.container.goal_service.view(goal_id)
        if result.reached:
            self._show_reached(view, chest_name=(
                result.chest.reward_name_snapshot if result.chest else None))
            return
        if result.rebased:
            self._show_carrier(
                view, "A new character takes over",
                f"picks the path up from {_amount(view.goal, view.goal.baseline_value)}. "
                "The track starts again from here.")
            return
        entry = result.entry
        moved = result.section_after - result.section_before
        message = f"{view.goal.name}: {_signed(entry.delta)} → {_amount(view.goal, entry.value_after)}"
        if moved > 0 and view.character:
            message += f" · {view.character.name} reached rank {result.section_after}"
        elif moved < 0:
            message += f" · back to section {result.section_after}"
        self.page.open(ft.SnackBar(
            content=ft.Text(message, color=TEXT), bgcolor=BG_2, action="Undo",
            duration=8000, on_action=lambda _: self._undo(goal_id),
        ))

    def _undo(self, goal_id: str) -> None:
        try:
            self.app.container.goal_service.undo_last_entry(goal_id)
        except TaskStampsError as error:
            self.app.error(error)
            return
        self.app.notify("Entry undone.")
        self.app.refresh_chest_count()
        self.refresh()

    # -- moments ------------------------------------------------------------

    def _show_carrier(self, view: GoalView, title: str, message: str) -> None:
        name = view.character.name if view.character else "No character is free right now"
        dialog = style_dialog(ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Column([
                goal_image(self.app.img_src(view.image_version_id), width=240),
                ft.Text(name, size=26, color=TEXT, font_family=SERIF),
                ft.Text(message if view.character else
                        "The goal keeps its numbers and takes the next free character.",
                        size=14, color=TEXT_DIM, text_align=ft.TextAlign.CENTER),
            ], tight=True, spacing=8, width=380,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        ))
        dialog.actions = [ft.TextButton("Close", on_click=lambda _: self.app.close_dialog(dialog))]
        self.app.open_dialog(dialog)

    def _show_reached(self, view: GoalView, chest_name: str | None = None) -> None:
        goal = view.goal
        lines: list[ft.Control] = [
            goal_image(self.app.img_src(view.goal_images.get(GOAL_SECTIONS)), width=260),
            eyebrow("Goal reached", ACCENT),
            ft.Text(goal.name, size=28, color=TEXT, font_family=SERIF),
            ft.Text(f"{view.character.name if view.character else 'You'} walked it to "
                    f"{_amount(goal, goal.current_value)}.", size=14, color=TEXT_DIM),
        ]
        if chest_name:
            lines.append(ft.Text(f"A chest dropped for {chest_name}.", size=14, color=ACCENT))
        elif view.leg is not None:
            chest = self.app.container.chests.chest_for_goal_leg(view.leg.id)
            if chest is not None:
                lines.append(ft.Text(
                    f"Its chest ({chest.reward_name_snapshot}) "
                    + ("was claimed." if chest.is_claimed else "is waiting in Vice Chests."),
                    size=14, color=TEXT_DIM if chest.is_claimed else ACCENT))
        lines.append(ft.Text("Extend the path to keep going with a new character and a new "
                             "goal, or finish it here.", size=13, color=MUTED_2,
                             text_align=ft.TextAlign.CENTER))
        dialog = style_dialog(ft.AlertDialog(
            modal=True,
            content=ft.Column(lines, tight=True, spacing=8, width=400,
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        ))

        def finish(_) -> None:
            self.app.close_dialog(dialog)
            try:
                self.app.container.goal_service.finish(goal.id)
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.app.notify(f"'{goal.name}' is finished.")
            self.refresh()

        dialog.actions = [
            ft.TextButton("Decide later", on_click=lambda _: self.app.close_dialog(dialog)),
            ft.TextButton("Finish the path", on_click=finish),
            ft.TextButton("Extend the path →", on_click=lambda _: (
                self.app.close_dialog(dialog), self._open_extend(view))),
        ]
        self.app.open_dialog(dialog)

    def _open_extend(self, view: GoalView) -> None:
        goal = view.goal
        target = _field("New goal", width=200, autofocus=True,
                        keyboard_type=ft.KeyboardType.NUMBER)
        reward = ft.Dropdown(
            label="Reward waiting at the end", width=400, border=ft.InputBorder.UNDERLINE,
            options=self._reward_options(),
        )
        if any(option.key == goal.reward_id for option in reward.options):
            reward.value = goal.reward_id
        dialog = style_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Extend the path"),
            content=ft.Column([
                ft.Text(f"A new character walks from {_amount(goal, goal.current_value)} to "
                        "wherever you set the goal next.", size=14, color=TEXT_DIM),
                target, reward,
            ], tight=True, spacing=14, width=420),
        ))

        def extend(_=None) -> None:
            try:
                value = _parse_number(target.value)
            except ValueError:
                self.app.error(ValueError("The new goal has to be a number."))
                return
            try:
                extended = self.app.container.goal_service.extend(goal.id, value, reward.value)
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.app.close_dialog(dialog)
            self.refresh()
            self._show_carrier(extended, "The path goes on",
                               f"walks '{goal.name}' on to {_amount(goal, value)}.")

        target.on_submit = extend
        dialog.actions = [
            ft.TextButton("Cancel", on_click=lambda _: self.app.close_dialog(dialog)),
            ft.TextButton("Extend", on_click=extend),
        ]
        self.app.open_dialog(dialog)

    def _confirm_remove(self, goal: Goal) -> None:
        def remove() -> None:
            try:
                self.app.container.goal_service.remove(goal.id)
            except TaskStampsError as error:
                self.app.error(error)
                return
            self.refresh()

        confirm_dialog(
            self.page, "Remove goal?",
            f"Remove '{goal.name}' and free its character? Chests it already earned stay "
            "in your inventory.",
            remove, "Remove")
