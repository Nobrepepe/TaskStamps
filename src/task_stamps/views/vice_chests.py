"""Define the nine reward slots and claim the chests they earn."""

from __future__ import annotations

import flet as ft

from task_stamps.components.common import confirm_dialog
from task_stamps.components.theme import (
    ACCENT, BAD, BG_HOVER_ALPHA, MUTED, MUTED_2, SERIF, TEXT, TEXT_DIM,
    eyebrow, eyebrow_row, hairline, style_dialog, text_action,
)
from task_stamps.domain.enums import CHEST_TIERS, CHEST_WEIGHTS, TaskWeight
from task_stamps.domain.exceptions import TaskStampsError
from task_stamps.domain.models import ViceReward
from task_stamps.services.chest_service import SlotView
from task_stamps.views.base import View

_WEIGHT_BLURB = {
    TaskWeight.MINOR: "Minor tasks — the everyday run.",
    TaskWeight.MEDIUM: "Medium tasks — the ones that take a real sitting.",
    TaskWeight.MAJOR: "Major tasks — the heavy lifts.",
}


class ViceChestsView(View):
    def build(self) -> ft.Control:
        self.summary = ft.Text()
        self.rows = ft.Column(spacing=0)
        header = ft.Column([
            eyebrow("Rewards"),
            ft.Text("Vice Chests", size=48, color=TEXT, font_family=SERIF),
            self.summary,
        ], spacing=10)
        return ft.Container(
            width=900,
            content=ft.Column([header, self.rows,
                ft.Text("Reaching streak 5, 10 or 15 on a Minor, Medium or Major task drops one "
                        "chest onto a random reward from that slot. Trivial tasks earn stamps only. "
                        "Defeating the daily Boss rolls one reward across all nine slots and "
                        "drops a chest on that — the harder the reward, the rarer it rolls.",
                        size=13, color=MUTED_2, width=580)], spacing=32, scroll=ft.ScrollMode.AUTO),
            padding=ft.padding.only(left=56, right=56, top=40, bottom=72), expand=True,
        )

    def refresh(self) -> None:
        service = self.app.container.chest_service
        slots = service.slots()
        waiting = service.unclaimed_total()
        defined = sum(len(slot.rewards) for slot in slots)
        self.summary.spans = [
            ft.TextSpan(str(waiting), ft.TextStyle(font_family=SERIF, size=26, color=ACCENT)),
            ft.TextSpan(f" chest{'' if waiting == 1 else 's'} waiting across {defined} "
                        f"reward{'' if defined == 1 else 's'}.",
                        ft.TextStyle(size=15, color=TEXT_DIM)),
        ]
        controls: list[ft.Control] = []
        for weight in CHEST_WEIGHTS:
            controls.append(ft.Container(height=10))
            controls.append(eyebrow_row(f"{weight.value} tasks"))
            controls.append(ft.Container(
                padding=ft.padding.only(top=8, bottom=4),
                content=ft.Text(_WEIGHT_BLURB[weight], size=13, color=MUTED_2),
            ))
            for tier in CHEST_TIERS:
                slot = next(s for s in slots if s.weight is weight and s.tier == tier)
                controls.extend(self._slot_block(slot))
        self.rows.controls = controls
        self.page.update()

    # -- the nine slots ----------------------------------------------------

    def _slot_block(self, slot: SlotView) -> list[ft.Control]:
        add = text_action(
            "Add a reward →",
            lambda _, s=slot: self._open_editor(weight=s.weight, tier=s.tier),
            size=12.5,
        )
        controls: list[ft.Control] = [
            ft.Container(
                padding=ft.padding.only(top=18, bottom=2),
                content=ft.Row([
                    ft.Text(f"Streak {slot.tier}", size=17, color=TEXT, font_family=SERIF),
                    ft.Container(expand=True),
                    add,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ),
            hairline(),
        ]
        if not slot.rewards:
            controls.append(ft.Container(
                padding=ft.padding.symmetric(vertical=16),
                content=ft.Text("Nothing here yet — this streak grants no chest until you add one.",
                                size=13, color=MUTED),
            ))
            controls.append(hairline())
            return controls
        for reward, count in zip(slot.rewards, slot.chest_counts):
            controls.extend([self._row(reward, count), hairline()])
        return controls

    def _row(self, reward: ViceReward, count: int) -> ft.Control:
        if count:
            waiting = f"{count} chest{'' if count == 1 else 's'} waiting."
            detail = f"{reward.description} · {waiting}" if reward.description else waiting
            detail_color = TEXT_DIM
            action: ft.Control = text_action(
                "Claim →", lambda _, item=reward: self._claim(item), color=ACCENT)
        else:
            detail = reward.description or "No chests yet."
            detail_color = MUTED_2
            action = ft.Container(width=96)
        edit_actions = ft.Row([
            text_action("Edit", lambda _, item=reward: self._open_editor(reward=item), size=12),
            text_action("Remove", lambda _, item=reward: self._confirm_remove(item), color=BAD, size=12),
        ], spacing=12, visible=False)
        row = ft.Container(
            padding=ft.padding.symmetric(vertical=20),
            content=ft.Row([
                ft.Column([
                    ft.Text(reward.name, size=22, color=TEXT if count else TEXT_DIM,
                            font_family=SERIF),
                    ft.Text(detail, size=13.5, color=detail_color), edit_actions,
                ], spacing=6, expand=True),
                ft.Text(spans=[
                    ft.TextSpan(str(count), ft.TextStyle(font_family=SERIF, size=24,
                                                         color=ACCENT if count else MUTED_2)),
                    ft.TextSpan("  CHEST" if count == 1 else "  CHESTS",
                                ft.TextStyle(size=12, color=MUTED_2, letter_spacing=1.2)),
                ], width=130, text_align=ft.TextAlign.RIGHT),
                ft.Container(content=action, width=96, alignment=ft.alignment.center_right),
            ], spacing=28, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )
        def hover(event) -> None:
            row.bgcolor = BG_HOVER_ALPHA if event.data == "true" else None
            edit_actions.visible = event.data == "true"
            row.update()
        row.on_hover = hover
        return row

    # -- editing -----------------------------------------------------------

    def _open_editor(
        self,
        *,
        reward: ViceReward | None = None,
        weight: TaskWeight | None = None,
        tier: int | None = None,
    ) -> None:
        weight = reward.task_weight if reward else weight
        tier = reward.tier if reward else tier
        assert weight is not None and tier is not None
        name = ft.TextField(label="Name", value=reward.name if reward else "")
        description = ft.TextField(label="Description", value=reward.description if reward else "",
                                   multiline=True, min_lines=2)
        weight_field = ft.Dropdown(
            label="Task weight", value=weight.value,
            options=[ft.dropdown.Option(w.value, w.value.title()) for w in CHEST_WEIGHTS])
        tier_field = ft.Dropdown(
            label="Streak", value=str(tier),
            options=[ft.dropdown.Option(str(t), f"Streak {t}") for t in CHEST_TIERS])
        dialog = style_dialog(ft.AlertDialog(
            modal=True, title=ft.Text("Edit reward" if reward else "Add reward"),
            content=ft.Column([name, description, ft.Row([weight_field, tier_field], spacing=12)],
                              width=480, tight=True, spacing=12)))
        def save(_) -> None:
            try:
                self.app.container.chest_service.save_reward(
                    reward.id if reward else None,
                    TaskWeight(weight_field.value or ""),
                    int(tier_field.value or ""),
                    name.value or "",
                    description.value or "",
                )
            except (ValueError, KeyError):
                self.app.error(ValueError("Pick a task weight and a streak.")); return
            except TaskStampsError as error:
                self.app.error(error); return
            self.app.close_dialog(dialog); self.refresh()
        dialog.actions = [ft.TextButton("Cancel", on_click=lambda _: self.app.close_dialog(dialog)),
                          ft.TextButton("Save", on_click=save)]
        self.app.open_dialog(dialog)

    def _confirm_remove(self, reward: ViceReward) -> None:
        confirm_dialog(
            self.page, "Remove reward?",
            f"Remove '{reward.name}'? Chests already earned for it keep their name in the history.",
            lambda: (self.app.container.chest_service.remove_reward(reward.id),
                     self.app.refresh_chest_count(), self.refresh()),
            "Remove")

    def _claim(self, reward: ViceReward) -> None:
        try:
            chest = self.app.container.chest_service.claim(reward.id)
        except TaskStampsError as error:
            self.app.error(error); return
        self.app.notify(f"Claimed {chest.reward_name_snapshot}. Enjoy it.")
        self.app.refresh_chest_count()
        self.refresh()
