"""「第五季」Agent 工具注册表"""

from tools.personal_tools import (
    find_mentors,
    find_users_by_tags,
    get_user_profile,
    manage_inspiration,
    manage_todo,
    upsert_user_profile,
)
from tools.project_tools import (
    add_project_member,
    add_project_update,
    advance_project_stage,
    awaken_project,
    create_project,
    get_project_detail,
    get_reminders,
    save_handover_package,
    save_match_log,
    school_issue_insight,
    search_projects,
    update_project,
)
from tools.legacy_tools import (
    discover_project_synergy,
    find_reference_cases,
    generate_handover_certificate,
    generate_seed_poster,
    get_my_awards,
    get_project_health,
    get_relay_stories,
    get_skill_graph,
    search_github_projects,
    vote_awaken_request,
)
from tools.message_tools import (
    check_my_inbox,
    send_message,
)
from tools.seed_tools import (
    import_from_github,
    match_seed_partners,
    read_upload,
    team_overview,
    upsert_profile,
)
from tools.personal_project_tools import (
    manage_personal_project,
    get_public_handover,
)

ALL_TOOLS = [
    # 个人板块
    upsert_user_profile,
    get_user_profile,
    find_users_by_tags,
    manage_todo,
    manage_inspiration,
    # 校园板块
    create_project,
    search_projects,
    get_project_detail,
    update_project,
    advance_project_stage,
    add_project_update,
    add_project_member,
    save_handover_package,
    awaken_project,
    save_match_log,
    get_reminders,
    school_issue_insight,
    # 传承扩展：故事墙 / 托付书 / 海报 / 巡检 / 图谱 / 投票 / 成就 / 协作发现 / 参考案例
    get_relay_stories,
    generate_handover_certificate,
    generate_seed_poster,
    get_project_health,
    get_skill_graph,
    vote_awaken_request,
    get_my_awards,
    discover_project_synergy,
    find_reference_cases,
    # 开放资源与前辈连接（v6.1）
    search_github_projects,
    find_mentors,
    # 留言信箱（v7.0）
    send_message,
    check_my_inbox,
    # 种子卡生态（v8.0）：导入建档 / 画像 / 种子对匹配 / 团队
    import_from_github,
    read_upload,
    upsert_profile,
    match_seed_partners,
    team_overview,
    # 个人项目库（v10.0）：完整项目信息 / 知颜生成交接包 / 公开授权 / 获取公开交接包
    manage_personal_project,
    get_public_handover,
]

__all__ = ["ALL_TOOLS"]
