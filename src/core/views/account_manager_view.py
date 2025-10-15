"""Account Manager View for multi-account management.

This view provides button-based UI for:
- Viewing all bound accounts
- Switching primary account
- Adding new accounts
- Removing accounts
"""

import discord
from typing import Any
import logging

logger = logging.getLogger(__name__)


class AccountManagerView(discord.ui.View):
    """Discord UI View for managing multiple LOL accounts.

    This view provides interactive account management:
    - Visual list of all bound accounts (primary marked with 💎)
    - Quick actions: Set as Primary, Remove Account
    - Add New Account button
    """

    def __init__(
        self,
        accounts: list[dict[str, Any]],
        user_id: str,
        db_adapter: Any,
        timeout: float = 300.0,  # 5 minutes
    ) -> None:
        """Initialize the account manager view.

        Args:
            accounts: List of user's bound accounts
            user_id: Discord user ID
            db_adapter: DatabaseAdapter instance
            timeout: View timeout in seconds
        """
        super().__init__(timeout=timeout)
        self.accounts = accounts
        self.user_id = user_id
        self.db = db_adapter

        # Dynamically create select menu for account selection
        if accounts:
            self._add_account_select()

    def _add_account_select(self) -> None:
        """Add account selection dropdown menu."""
        options: list[discord.SelectOption] = []

        for idx, account in enumerate(self.accounts, start=1):
            summoner_name = account.get("summoner_name", "Unknown")
            nickname = account.get("nickname")
            is_primary = account.get("is_primary", False)
            region = account.get("region", "??").upper()

            # Format label
            icon = "💎" if is_primary else "🔹"
            if nickname:
                label = f"{icon} {nickname} - {summoner_name}"
            else:
                acc_label = "主号" if is_primary else f"小号{idx-1}"
                label = f"{icon} {acc_label} - {summoner_name}"

            # Format description
            desc = f"{region} 服务器"
            if is_primary:
                desc += " · 当前主账号"

            options.append(
                discord.SelectOption(
                    label=label[:100],  # Discord max 100 chars
                    value=str(idx - 1),  # 0-based index as value
                    description=desc[:100],
                    emoji="💎" if is_primary else "🔹",
                )
            )

        # Create select menu
        select = discord.ui.Select(
            placeholder="选择要管理的账号...",
            options=options[:25],  # Discord max 25 options
            custom_id="account_select",
            row=0,
        )
        select.callback = self._account_selected
        self.add_item(select)

    async def _account_selected(self, interaction: discord.Interaction) -> None:
        """Handle account selection from dropdown."""
        selected_idx = int(interaction.data["values"][0])
        selected_account = self.accounts[selected_idx]

        # Show account details with action buttons
        await self._show_account_details(interaction, selected_account, selected_idx)

    async def _show_account_details(
        self, interaction: discord.Interaction, account: dict[str, Any], index: int
    ) -> None:
        """Show detailed account info with action buttons."""
        summoner_name = account.get("summoner_name", "Unknown")
        nickname = account.get("nickname")
        is_primary = account.get("is_primary", False)
        region = account.get("region", "??").upper()
        created_at = account.get("created_at")

        # Create details embed
        embed = discord.Embed(
            title=f"{'💎' if is_primary else '🔹'} 账号详情",
            description=f"**{nickname or summoner_name}**",
            color=0xFFD700 if is_primary else 0x5865F2,
        )

        embed.add_field(name="Riot ID", value=summoner_name, inline=True)
        embed.add_field(name="服务器", value=region, inline=True)
        embed.add_field(
            name="状态",
            value="主账号 💎" if is_primary else f"小号 #{index}",
            inline=True,
        )

        if nickname:
            embed.add_field(name="昵称", value=nickname, inline=True)

        if created_at:
            timestamp = f"<t:{int(created_at.timestamp())}:R>"
            embed.add_field(name="绑定时间", value=timestamp, inline=True)

        # Create action buttons view
        action_view = AccountActionView(
            account=account,
            account_index=index,
            user_id=self.user_id,
            db_adapter=self.db,
            is_primary=is_primary,
        )

        await interaction.response.send_message(
            embed=embed,
            view=action_view,
            ephemeral=True,
        )

    @discord.ui.button(
        label="➕ 添加新账号",
        style=discord.ButtonStyle.success,
        row=1,
        custom_id="add_account",
    )
    async def add_account_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Handle add new account button click."""
        from src.core.views.bind_modal import EnhancedBindModal

        # Show bind modal for adding secondary account
        bind_modal = EnhancedBindModal(user_id=self.user_id)

        # Customize modal for secondary account
        bind_modal.title = "🔹 添加小号"

        await interaction.response.send_modal(bind_modal)

    @discord.ui.button(
        label="🔄 刷新列表",
        style=discord.ButtonStyle.secondary,
        row=1,
        custom_id="refresh_accounts",
    )
    async def refresh_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Refresh account list."""
        # Fetch updated accounts
        updated_accounts = await self.db.list_user_accounts(self.user_id)

        if not updated_accounts:
            embed = discord.Embed(
                title="⚠️ 无绑定账号",
                description="你还没有绑定任何账号。\n使用下方按钮添加账号吧！",
                color=0xF39C12,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Update internal state
        self.accounts = updated_accounts
        self.clear_items()
        self._add_account_select()
        self.add_item(self.children[1])  # Re-add add button
        self.add_item(self.children[2])  # Re-add refresh button

        # Send updated embed
        embed = self._create_account_list_embed(updated_accounts)
        await interaction.response.edit_message(embed=embed, view=self)

    def _create_account_list_embed(self, accounts: list[dict[str, Any]]) -> discord.Embed:
        """Create embed showing all accounts."""
        embed = discord.Embed(
            title="🎮 账号管理",
            description=f"你已绑定 **{len(accounts)}** 个账号",
            color=0x5865F2,
        )

        for idx, account in enumerate(accounts, start=1):
            summoner_name = account.get("summoner_name", "Unknown")
            nickname = account.get("nickname")
            is_primary = account.get("is_primary", False)
            region = account.get("region", "??").upper()

            icon = "💎" if is_primary else "🔹"
            label = nickname or (f"账号 #{idx}")
            status = "主账号" if is_primary else "小号"

            embed.add_field(
                name=f"{icon} {label}",
                value=f"`{summoner_name}`\n{region} · {status}",
                inline=True,
            )

        embed.set_footer(text="使用下拉菜单选择账号进行管理")
        return embed


class AccountActionView(discord.ui.View):
    """Action buttons for a specific account."""

    def __init__(
        self,
        account: dict[str, Any],
        account_index: int,
        user_id: str,
        db_adapter: Any,
        is_primary: bool,
        timeout: float = 180.0,
    ) -> None:
        """Initialize account action view."""
        super().__init__(timeout=timeout)
        self.account = account
        self.account_index = account_index
        self.user_id = user_id
        self.db = db_adapter

        # Hide "Set as Primary" button if already primary
        if is_primary:
            self.set_primary_button.disabled = True
            self.set_primary_button.label = "✅ 已是主账号"

    @discord.ui.button(
        label="💎 设为主账号",
        style=discord.ButtonStyle.primary,
        custom_id="set_primary",
    )
    async def set_primary_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Set this account as primary."""
        puuid = self.account.get("riot_puuid")
        if not puuid:
            await interaction.response.send_message(
                "❌ 账号数据异常，请联系管理员。",
                ephemeral=True,
            )
            return

        try:
            success = await self.db.set_primary_account(self.user_id, puuid)

            if success:
                embed = discord.Embed(
                    title="✅ 主账号已更换",
                    description=f"**{self.account['summoner_name']}** 现在是你的主账号。",
                    color=0x2ECC71,
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    "❌ 设置失败，请稍后重试。",
                    ephemeral=True,
                )

        except Exception as e:
            logger.error(f"Error setting primary account: {e}")
            await interaction.response.send_message(
                f"❌ 发生错误：{type(e).__name__}",
                ephemeral=True,
            )

    @discord.ui.button(
        label="🗑️ 删除账号",
        style=discord.ButtonStyle.danger,
        custom_id="remove_account",
    )
    async def remove_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Remove this account (with confirmation)."""
        puuid = self.account.get("riot_puuid")
        is_primary = self.account.get("is_primary", False)

        # Show confirmation
        embed = discord.Embed(
            title="⚠️ 确认删除",
            description=(
                f"确定要删除账号 **{self.account['summoner_name']}** 吗？\n\n"
                f"{'⚠️ 这是你的主账号，删除后会自动将下一个账号设为主账号。' if is_primary else ''}"
            ),
            color=0xE74C3C,
        )

        confirm_view = ConfirmDeleteView(
            puuid=puuid,
            user_id=self.user_id,
            db_adapter=self.db,
            summoner_name=self.account["summoner_name"],
        )

        await interaction.response.send_message(
            embed=embed,
            view=confirm_view,
            ephemeral=True,
        )


class ConfirmDeleteView(discord.ui.View):
    """Confirmation view for account deletion."""

    def __init__(
        self,
        puuid: str,
        user_id: str,
        db_adapter: Any,
        summoner_name: str,
        timeout: float = 60.0,
    ) -> None:
        """Initialize confirmation view."""
        super().__init__(timeout=timeout)
        self.puuid = puuid
        self.user_id = user_id
        self.db = db_adapter
        self.summoner_name = summoner_name

    @discord.ui.button(
        label="✅ 确认删除",
        style=discord.ButtonStyle.danger,
        custom_id="confirm_delete",
    )
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Confirm account deletion."""
        try:
            success = await self.db.remove_account(self.user_id, self.puuid)

            if success:
                embed = discord.Embed(
                    title="✅ 账号已删除",
                    description=f"**{self.summoner_name}** 已从你的账号列表中移除。",
                    color=0x2ECC71,
                )
                # Disable all buttons
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.response.send_message(
                    "❌ 删除失败，请稍后重试。",
                    ephemeral=True,
                )

        except Exception as e:
            logger.error(f"Error removing account: {e}")
            await interaction.response.send_message(
                f"❌ 发生错误：{type(e).__name__}",
                ephemeral=True,
            )

    @discord.ui.button(
        label="❌ 取消",
        style=discord.ButtonStyle.secondary,
        custom_id="cancel_delete",
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        """Cancel deletion."""
        embed = discord.Embed(
            title="已取消",
            description="账号删除操作已取消。",
            color=0x95A5A6,
        )
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)
