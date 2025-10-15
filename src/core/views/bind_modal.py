"""Enhanced Bind Modal for first-time account setup.

This modal collects comprehensive user information during first binding:
- Riot ID (Name#TAG)
- Server region
- Main role preference
- Optional: Add secondary accounts
"""

import discord
from typing import Any


class EnhancedBindModal(discord.ui.Modal, title="🎮 绑定 LOL 账号"):
    """Enhanced account binding modal for comprehensive first-time setup.

    This modal is shown when user runs /bind for the first time,
    collecting all necessary information in one interactive session.

    Design Philosophy:
    - Minimize future friction by collecting complete data upfront
    - Use clear Chinese labels with English placeholders
    - Provide helpful validation feedback
    """

    # Primary Riot ID
    riot_id = discord.ui.TextInput(
        label="Riot ID（游戏名#标签）*",
        placeholder="格式: 游戏名#TAG (如: Fuji shanxia#NA1)",
        required=True,
        min_length=3,
        max_length=32,
        style=discord.TextStyle.short,
    )

    # Server region
    region = discord.ui.TextInput(
        label="主要服务器*",
        placeholder="北美=NA | 韩国=KR | 欧西=EUW | 欧北=EUNE",
        required=True,
        min_length=2,
        max_length=10,
        style=discord.TextStyle.short,
    )

    # Main role (supports multiple selections)
    main_role = discord.ui.TextInput(
        label="常用位置（可选，支持多选）",
        placeholder="示例: mid | mid/jungle | top,mid | support",
        required=False,
        max_length=50,
        style=discord.TextStyle.short,
    )

    # Nickname (optional)
    nickname = discord.ui.TextInput(
        label="昵称（可选，用于播报）",
        placeholder="给这个账号起个名字，如: 主号、冲分号、娱乐号",
        required=False,
        max_length=32,
        style=discord.TextStyle.short,
    )

    def __init__(self, user_id: str, on_success_callback: Any = None) -> None:
        """Initialize the bind modal.

        Args:
            user_id: Discord user ID who is binding the account
            on_success_callback: Optional async callback function to call after successful validation
        """
        super().__init__()
        self.user_id = user_id
        self.bind_data: dict[str, Any] | None = None
        self.on_success_callback = on_success_callback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle modal submission with validation.

        This method validates inputs and stores the bind data for
        external processing by discord_adapter.
        """
        # Defer response quickly (<3s rule)
        await interaction.response.defer(ephemeral=True)

        # Validate Riot ID format
        riot_id_value = self.riot_id.value.strip()
        if "#" not in riot_id_value:
            error_embed = discord.Embed(
                title="❌ Riot ID 格式错误",
                description=(
                    "**Riot ID 必须包含 `#` 符号**\n\n"
                    "✅ 正确格式示例:\n"
                    "• `Faker#KR1`\n"
                    "• `Hide on bush#KR1`\n"
                    "• `Fuji shanxia#NA1`\n\n"
                    f"❌ 您输入的: `{riot_id_value}`\n"
                    "请重新打开 /bind 命令并使用正确格式。"
                ),
                color=0xE74C3C,
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        # Parse Riot ID
        parts = riot_id_value.split("#", 1)
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            error_embed = discord.Embed(
                title="❌ Riot ID 格式错误",
                description=(
                    "**格式必须是: 游戏名#标签**\n\n"
                    "✅ 正确示例:\n"
                    "• `Faker#KR1` (游戏名=Faker, 标签=KR1)\n"
                    "• `Fuji shanxia#NA1` (游戏名=Fuji shanxia, 标签=NA1)\n\n"
                    f"❌ 您输入的: `{riot_id_value}`\n"
                    "请确保 # 号前后都有内容。"
                ),
                color=0xE74C3C,
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        game_name = parts[0].strip()
        tag_line = parts[1].strip().upper()

        # Validate region
        region_value = self.region.value.strip().lower()
        valid_regions = [
            "na",
            "na1",
            "euw",
            "euw1",
            "eune",
            "eun1",
            "kr",
            "br",
            "br1",
            "lan",
            "la1",
            "las",
            "la2",
            "oce",
            "oc1",
            "ru",
            "tr",
            "tr1",
            "jp",
            "jp1",
            "ph",
            "ph2",
            "sg",
            "sg2",
            "th",
            "th2",
            "tw",
            "tw2",
            "vn",
            "vn2",
        ]

        # Normalize region code
        region_map = {
            "na": "na1",
            "euw": "euw1",
            "eune": "eun1",
            "oce": "oc1",
            "br": "br1",
            "lan": "la1",
            "las": "la2",
            "jp": "jp1",
            "ph": "ph2",
            "sg": "sg2",
            "th": "th2",
            "tw": "tw2",
            "vn": "vn2",
            "tr": "tr1",
        }
        region_normalized = region_map.get(region_value, region_value)

        if region_normalized not in valid_regions:
            error_embed = discord.Embed(
                title="❌ 服务器区域无效",
                description=(
                    f"**不支持的服务器: `{region_value}`**\n\n"
                    "✅ 支持的服务器列表:\n\n"
                    "**亚洲:**\n• `KR` - 韩国\n• `JP` - 日本\n• `PH`, `SG`, `TH`, `TW`, `VN` - 东南亚\n\n"
                    "**欧洲:**\n• `EUW` - 欧西\n• `EUNE` - 欧北\n• `TR` - 土耳其\n• `RU` - 俄罗斯\n\n"
                    "**美洲:**\n• `NA` - 北美\n• `BR` - 巴西\n• `LAN` - 拉丁美洲北\n• `LAS` - 拉丁美洲南\n\n"
                    "**大洋洲:**\n• `OCE` - 大洋洲\n\n"
                    "💡 提示: 输入两个字母即可，如 NA、KR、EUW"
                ),
                color=0xE74C3C,
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        # Validate main_role if provided (supports multiple roles)
        main_role_value = self.main_role.value.strip().lower() if self.main_role.value else None
        validated_roles = None

        if main_role_value:
            valid_roles = ["top", "jungle", "mid", "bot", "support", "fill"]

            # Parse multiple roles (support comma, slash, or space as separator)
            import re

            role_list = re.split(r"[,/\s]+", main_role_value)
            role_list = [r.strip() for r in role_list if r.strip()]

            # Validate each role
            invalid_roles = [r for r in role_list if r not in valid_roles]
            if invalid_roles:
                error_embed = discord.Embed(
                    title="❌ 位置选择无效",
                    description=(
                        f"**不支持的位置: `{', '.join(invalid_roles)}`**\n\n"
                        "✅ 有效的位置选项:\n"
                        "• `top` - 上路\n"
                        "• `jungle` - 打野\n"
                        "• `mid` - 中路\n"
                        "• `bot` - 下路 (ADC)\n"
                        "• `support` - 辅助\n"
                        "• `fill` - 补位\n\n"
                        "💡 多个位置可用逗号、斜杠或空格分隔\n"
                        "例如: `mid jungle` 或 `mid/jungle` 或 `mid,jungle`"
                    ),
                    color=0xE74C3C,
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                return

            # Store as comma-separated string for database
            validated_roles = ",".join(role_list)

        # Store validated bind data for external processing
        self.bind_data = {
            "game_name": game_name,
            "tag_line": tag_line,
            "region": region_normalized,
            "main_role": validated_roles,  # Comma-separated list of validated roles
            "nickname": self.nickname.value.strip() if self.nickname.value else None,
        }

        # Call success callback if provided
        if self.on_success_callback:
            await self.on_success_callback(interaction, self.bind_data)
        # Otherwise, success message will be sent by discord_adapter after Riot API verification
