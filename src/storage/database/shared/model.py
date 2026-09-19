from coze_coding_dev_sdk.database import Base

from typing import Optional
import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Double, ForeignKey, Index, Integer, Numeric, PrimaryKeyConstraint, String, Table, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, OID
from sqlalchemy.orm import Mapped, mapped_column

class HealthCheck(Base):
    __tablename__ = 'health_check'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='health_check_pkey'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('now()'))


t_pg_stat_statements = Table(
    'pg_stat_statements', Base.metadata,
    Column('userid', OID),
    Column('dbid', OID),
    Column('toplevel', Boolean),
    Column('queryid', BigInteger),
    Column('query', Text),
    Column('plans', BigInteger),
    Column('total_plan_time', Double(53)),
    Column('min_plan_time', Double(53)),
    Column('max_plan_time', Double(53)),
    Column('mean_plan_time', Double(53)),
    Column('stddev_plan_time', Double(53)),
    Column('calls', BigInteger),
    Column('total_exec_time', Double(53)),
    Column('min_exec_time', Double(53)),
    Column('max_exec_time', Double(53)),
    Column('mean_exec_time', Double(53)),
    Column('stddev_exec_time', Double(53)),
    Column('rows', BigInteger),
    Column('shared_blks_hit', BigInteger),
    Column('shared_blks_read', BigInteger),
    Column('shared_blks_dirtied', BigInteger),
    Column('shared_blks_written', BigInteger),
    Column('local_blks_hit', BigInteger),
    Column('local_blks_read', BigInteger),
    Column('local_blks_dirtied', BigInteger),
    Column('local_blks_written', BigInteger),
    Column('temp_blks_read', BigInteger),
    Column('temp_blks_written', BigInteger),
    Column('shared_blk_read_time', Double(53)),
    Column('shared_blk_write_time', Double(53)),
    Column('local_blk_read_time', Double(53)),
    Column('local_blk_write_time', Double(53)),
    Column('temp_blks_read_time', Double(53)),
    Column('temp_blk_write_time', Double(53)),
    Column('wal_records', BigInteger),
    Column('wal_fpi', BigInteger),
    Column('wal_bytes', Numeric),
    Column('jit_functions', BigInteger),
    Column('jit_generation_time', Double(53)),
    Column('jit_inlining_count', BigInteger),
    Column('jit_inlining_time', Double(53)),
    Column('jit_optimization_count', BigInteger),
    Column('jit_optimization_time', Double(53)),
    Column('jit_emission_count', BigInteger),
    Column('jit_emission_time', Double(53)),
    Column('jit_deform_count', BigInteger),
    Column('jit_deform_time', Double(53)),
    Column('stats_since', DateTime(True)),
    Column('minmax_stats_since', DateTime(True))
)


t_pg_stat_statements_info = Table(
    'pg_stat_statements_info', Base.metadata,
    Column('dealloc', BigInteger),
    Column('stats_reset', DateTime(True))
)


# ============================================================================
# 「第五季·续种」业务表（fs_ = fifth season）
# ============================================================================

class FsUser(Base):
    """用户档案：昵称建档、能力/兴趣标签（夏·匹配与第五季·唤醒的数据基础）"""
    __tablename__ = 'fs_users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nickname: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="用户昵称（档案识别键）")
    grade: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="年级/届别")
    major: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="专业")
    skill_tags: Mapped[list] = mapped_column(ARRAY(String(64)), server_default='{}', nullable=False, comment="能力标签")
    interest_tags: Mapped[list] = mapped_column(ARRAY(String(64)), server_default='{}', nullable=False, comment="兴趣标签")
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="个人简介")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), nullable=True)

    __table_args__ = (
        Index('fs_users_nickname_idx', 'nickname'),
    )


class FsProject(Base):
    """项目种子卡：四季状态机 spring/summer/autumn/winter + fifth(重生)"""
    __tablename__ = 'fs_projects'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False, comment="项目标题")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="项目简介")
    domain_tags: Mapped[list] = mapped_column(ARRAY(String(64)), server_default='{}', nullable=False, comment="领域标签")
    required_skills: Mapped[list] = mapped_column(ARRAY(String(64)), server_default='{}', nullable=False, comment="所需能力标签")
    stage: Mapped[str] = mapped_column(String(16), nullable=False, server_default='spring', comment="阶段: spring/summer/autumn/winter/fifth")
    founder_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_users.id'), nullable=False, comment="发起人")
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_users.id'), nullable=False, comment="当前负责人")
    hibernate_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="休眠原因（冬·蛰伏）")
    hibernate_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), nullable=True, comment="休眠时间")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), nullable=True)

    __table_args__ = (
        Index('fs_projects_stage_idx', 'stage'),
        Index('fs_projects_founder_id_idx', 'founder_id'),
        Index('fs_projects_owner_id_idx', 'owner_id'),
        Index('fs_projects_stage_updated_idx', 'stage', 'updated_at'),
    )


class FsInspiration(Base):
    """灵感记录：碎片想法，可转化为项目种子"""
    __tablename__ = 'fs_inspirations'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_users.id'), nullable=False, comment="记录人")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="灵感内容")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default='fragment', comment="状态: fragment/converted")
    project_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('fs_projects.id'), nullable=True, comment="转化后的项目id")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), nullable=True)

    __table_args__ = (
        Index('fs_inspirations_user_id_idx', 'user_id'),
        Index('fs_inspirations_user_status_idx', 'user_id', 'status'),
    )


class FsTodo(Base):
    """待办事项：支持与项目关联"""
    __tablename__ = 'fs_todos'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_users.id'), nullable=False, comment="所属用户")
    title: Mapped[str] = mapped_column(String(256), nullable=False, comment="待办标题")
    due_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), nullable=True, comment="截止时间")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default='pending', comment="状态: pending/doing/done")
    project_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('fs_projects.id'), nullable=True, comment="关联项目id")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), nullable=True)

    __table_args__ = (
        Index('fs_todos_user_status_idx', 'user_id', 'status'),
        Index('fs_todos_user_due_idx', 'user_id', 'due_at'),
        Index('fs_todos_project_id_idx', 'project_id'),
    )


class FsProjectMember(Base):
    """项目成员：夏·生长的组队结果"""
    __tablename__ = 'fs_project_members'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_projects.id'), nullable=False, comment="项目id")
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_users.id'), nullable=False, comment="成员用户id")
    role: Mapped[str] = mapped_column(String(64), nullable=False, comment="成员角色")
    joined_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False)

    __table_args__ = (
        Index('fs_pm_project_id_idx', 'project_id'),
        Index('fs_pm_user_id_idx', 'user_id'),
        Index('fs_pm_project_user_idx', 'project_id', 'user_id'),
    )


class FsProjectUpdate(Base):
    """项目动态日志：秋·沉淀的原始素材"""
    __tablename__ = 'fs_project_updates'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_projects.id'), nullable=False, comment="项目id")
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_users.id'), nullable=False, comment="作者用户id")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="动态内容")
    stage: Mapped[str] = mapped_column(String(16), nullable=False, server_default='summer', comment="记录时的项目阶段")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False)

    __table_args__ = (
        Index('fs_pu_project_created_idx', 'project_id', 'created_at'),
        Index('fs_pu_author_id_idx', 'author_id'),
    )


class FsHandoverPackage(Base):
    """交接包：五段式 JSON（成果/经验/踩坑/遗留问题/可复用资源）"""
    __tablename__ = 'fs_handover_packages'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_projects.id'), nullable=False, comment="项目id")
    achievements: Mapped[str] = mapped_column(Text, nullable=False, comment="项目成果（JSON数组字符串）")
    experience: Mapped[str] = mapped_column(Text, nullable=False, comment="执行经验（JSON数组字符串）")
    pitfalls: Mapped[str] = mapped_column(Text, nullable=False, comment="踩坑总结（JSON数组字符串）")
    remaining_issues: Mapped[str] = mapped_column(Text, nullable=False, comment="遗留问题（JSON数组字符串）")
    reusable_resources: Mapped[str] = mapped_column(Text, nullable=False, comment="可复用资源（JSON数组字符串）")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False)

    __table_args__ = (
        Index('fs_hp_project_created_idx', 'project_id', 'created_at'),
    )


class FsAwakenRecord(Base):
    """唤醒记录：第五季·重生的核心数据（答辩展示用）"""
    __tablename__ = 'fs_awaken_records'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_projects.id'), nullable=False, comment="被唤醒的休眠项目id")
    successor_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_users.id'), nullable=False, comment="接力人用户id")
    match_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="匹配理由")
    awakened_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False)

    __table_args__ = (
        Index('fs_ar_project_id_idx', 'project_id'),
        Index('fs_ar_successor_id_idx', 'successor_id'),
    )


class FsMatchLog(Base):
    """匹配日志：双向匹配的效果验证数据"""
    __tablename__ = 'fs_match_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="匹配类型: user_to_project/project_to_user/partner")
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('fs_users.id'), nullable=True, comment="发起匹配的用户id")
    project_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('fs_projects.id'), nullable=True, comment="涉及项目id")
    matched_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('fs_users.id'), nullable=True, comment="被匹配用户id（找伙伴场景）")
    match_score: Mapped[Optional[float]] = mapped_column(Double(53), nullable=True, comment="匹配分 0-100")
    match_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="匹配理由")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False)

    __table_args__ = (
        Index('fs_ml_user_id_idx', 'user_id'),
        Index('fs_ml_project_id_idx', 'project_id'),
        Index('fs_ml_created_idx', 'created_at'),
    )


# ============================================================================
# v3 新增四表
# 此前本文件只定义了 9 张业务表，而代码实际读写 13 张——fs_stories / fs_awards /
# fs_user_awards / fs_votes 一直缺席，导致 ORM 元数据与真实库结构不一致。
# 以下按代码中的实际读写字段补齐。
# ============================================================================

class FsStory(Base):
    """传承故事卡：唤醒接棒成功后自动生成，展示在主页传承故事墙"""
    __tablename__ = 'fs_stories'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    awaken_record_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('fs_awaken_records.id'), nullable=True, comment="来源唤醒记录")
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_projects.id'), nullable=False, comment="项目id")
    project_title: Mapped[str] = mapped_column(String(128), nullable=False, comment="项目标题（冗余，便于故事墙直读）")
    founder_nickname: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="原发起人昵称")
    successor_nickname: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="接棒者昵称")
    match_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="匹配理由")
    story_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="故事正文")
    # 注意：此处是 jsonb 列表（空值应写 []，不是 {}）
    highlights: Mapped[Optional[list]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"), nullable=True, comment="前人留下的高光成果")
    period_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="沉睡天数")
    is_featured: Mapped[bool] = mapped_column(Boolean, server_default=text('false'), nullable=False, comment="是否精选")
    likes: Mapped[int] = mapped_column(Integer, server_default=text('0'), nullable=False, comment="点赞数")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False)

    __table_args__ = (
        Index('fs_stories_project_id_idx', 'project_id'),
        Index('fs_stories_created_idx', 'created_at'),
    )


class FsAward(Base):
    """成就定义（勋章字典表）"""
    __tablename__ = 'fs_awards'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="成就代码（唯一）")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="勋章名称")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="成就说明")
    icon: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, comment="勋章图标")
    category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="分类：发起/沉淀/接棒/助推")
    points: Mapped[int] = mapped_column(Integer, server_default=text('0'), nullable=False, comment="贡献值")


class FsUserAward(Base):
    """用户已获得的成就（同一用户同一勋章唯一）"""
    __tablename__ = 'fs_user_awards'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_users.id'), nullable=False, comment="用户id")
    award_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_awards.id'), nullable=False, comment="成就id")
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="获得原因")
    awarded_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False)

    __table_args__ = (
        Index('fs_user_awards_user_id_idx', 'user_id'),
        Index('fs_user_awards_user_award_uniq', 'user_id', 'award_id', unique=True),
    )


class FsVote(Base):
    """休眠种子的唤醒需求投票（一人一项目一票，靠唯一约束防刷票）"""
    __tablename__ = 'fs_votes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey('fs_projects.id'), nullable=False, comment="被投票的休眠项目id")
    voter_nickname: Mapped[str] = mapped_column(String(64), nullable=False, comment="投票人昵称（须已建档）")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False)

    __table_args__ = (
        Index('fs_votes_project_id_idx', 'project_id'),
        Index('fs_votes_project_voter_uniq', 'project_id', 'voter_nickname', unique=True),
    )


class FsReferenceCase(Base):
    """参考案例库：全国高校/公益机构真实已完成的项目，供用户检索类似方向的借鉴案例"""
    __tablename__ = 'fs_reference_cases'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False, comment="案例标题")
    org: Mapped[str] = mapped_column(String(128), nullable=False, comment="发起学校/机构")
    summary: Mapped[str] = mapped_column(Text, nullable=False, comment="项目简介")
    domain_tags: Mapped[list] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"), nullable=False, comment="领域标签")
    achievements: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="真实成果（含数字）")
    award: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="获奖情况")
    url: Mapped[str] = mapped_column(String(512), nullable=False, comment="可跳转的网页链接")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False)

    __table_args__ = (
        Index('fs_reference_cases_domain_idx', 'domain_tags'),
    )
