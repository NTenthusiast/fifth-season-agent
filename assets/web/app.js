(function () {
  "use strict";

  /* ==================== 元素引用 ==================== */
  var introView = document.getElementById("view-intro");
  var chatView = document.getElementById("view-chat");

  var statUsers = document.getElementById("stat-users");
  var statProjects = document.getElementById("stat-projects");
  var statAwaken = document.getElementById("stat-awaken");

  var chatBox = document.getElementById("chat-messages");
  var inputEl = document.getElementById("chat-input");
  var sendBtn = document.getElementById("btn-send");
  var resetBtn = document.getElementById("btn-reset");
  var statusEl = document.getElementById("chat-status");

  /* ==================== 会话管理 ==================== */
  var STORE_KEY = "fifth_season_view";       // 当前所在视图
  var SESSION_KEY = "fifth_season_session";  // 会话 id（对应智能体记忆线程）
  var HISTORY_KEY = "fifth_season_history";  // 页面气泡历史

  /* ==================== v7.0 登录态（昵称 + 六位传承码） ==================== */
  var AUTH_KEY = "fifth_season_auth";  // {nickname, code, user}
  var auth = null;

  function loadAuth() {
    try { auth = JSON.parse(localStorage.getItem(AUTH_KEY) || "null"); }
    catch (e) { auth = null; }
    return auth;
  }
  function saveAuth(next) {
    var prevNick = auth ? auth.nickname : null;
    var nextNick = next ? next.nickname : null;
    auth = next;
    try {
      if (next) {
        localStorage.setItem(AUTH_KEY, JSON.stringify(next));
        // 认证 cookie：浏览器 fetch 不允许中文 header 值，改走 cookie（URL 编码，同源自动携带）
        document.cookie = "fs_auth=" + encodeURIComponent(JSON.stringify({ n: next.nickname, c: next.code })) + "; path=/; max-age=604800; SameSite=Strict";
      } else {
        localStorage.removeItem(AUTH_KEY);
        document.cookie = "fs_auth=; path=/; max-age=0; SameSite=Strict";
      }
    } catch (e) {}
    // v9.0 用户隔离：切换账号（含登出）时清掉上一账号的对话残留，不同本地用户互不可见
    if (prevNick !== nextNick) {
      resetSession();
      if (chatBox) { chatBox.innerHTML = ""; }
      var introHint = document.getElementById("chat-intro-hint") || document.getElementById("intro-chat-hint");
      if (introHint) { introHint.hidden = false; }
    }
    renderNavAuth();
  }
  function authHeaders() {
    // header 仅在值可安全传输时附带（ASCII 昵称走 header，中文昵称依赖 cookie）
    if (auth && /^[\x20-\x7E]+$/.test(auth.nickname)) {
      return { "X-FS-Nickname": auth.nickname, "X-FS-Code": auth.code };
    }
    return {};
  }
  function renderNavAuth() {
    var loginBtn = document.getElementById("nav-auth-login");
    var userBox = document.getElementById("nav-auth-user");
    var nameEl = document.getElementById("nav-user-name");
    if (auth) {
      if (loginBtn) { loginBtn.hidden = true; }
      if (userBox) { userBox.hidden = false; }
      if (nameEl) { nameEl.textContent = auth.nickname; }
      refreshUnread();
    } else {
      if (loginBtn) { loginBtn.hidden = false; }
      if (userBox) { userBox.hidden = true; }
    }
  }
  function refreshUnread() {
    if (!auth) { return; }
    fetch("/api/auth/me", { headers: authHeaders() })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        var badge = document.getElementById("bell-badge");
        if (!badge) { return; }
        var n = (d && typeof d.unread === "number") ? d.unread : 0;
        badge.textContent = n > 99 ? "99+" : String(n);
        badge.hidden = n <= 0;
      })
      .catch(function () {});
  }

  /* 认证弹窗：返回 Promise<true 登录成功 / null 取消> */
  var authModal = document.getElementById("auth-modal");
  var authResolve = null;
  var authGrade = 2024;

  function requireAuth(reason) {
    return new Promise(function (resolve) {
      if (auth) { resolve(true); return; }
      authResolve = resolve;
      openAuthModal(reason || "");
    });
  }
  function openAuthModal(reason) {
    if (!authModal) { return; }
    var sub = document.getElementById("auth-sub");
    if (sub && reason) { sub.textContent = reason; }
    switchAuthTab("login");
    showAuthPanel("form");
    clearAuthErrors();
    authModal.hidden = false;
    document.body.style.overflow = "hidden";
    setTimeout(function () {
      var el = document.getElementById("login-nick");
      if (el) { el.focus(); }
    }, 40);
  }
  function closeAuthModal(result) {
    if (!authModal) { return; }
    authModal.hidden = true;
    document.body.style.overflow = "";
    if (authResolve) { authResolve(result); authResolve = null; }
  }
  function switchAuthTab(tab) {
    var tabs = document.querySelectorAll("[data-auth-tab]");
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].classList.toggle("active", tabs[i].getAttribute("data-auth-tab") === tab);
    }
    var lf = document.getElementById("auth-login-form");
    var rf = document.getElementById("auth-register-form");
    if (lf) { lf.hidden = tab !== "login"; }
    if (rf) { rf.hidden = tab !== "register"; }
  }
  function showAuthPanel(which) {
    var lf = document.getElementById("auth-login-form");
    var rf = document.getElementById("auth-register-form");
    var tabs = document.getElementById("auth-tabs");
    var reveal = document.getElementById("auth-code-reveal");
    var head = document.querySelector("#auth-modal .auth-head h3");
    if (which === "code") {
      if (lf) { lf.hidden = true; }
      if (rf) { rf.hidden = true; }
      if (tabs) { tabs.style.display = "none"; }
      if (reveal) { reveal.hidden = false; }
      if (head) { head.textContent = "传承码已生成"; }
    } else {
      if (reveal) { reveal.hidden = true; }
      if (tabs) { tabs.style.display = ""; }
      if (head) { head.textContent = "回到第五季"; }
    }
  }
  function clearAuthErrors() {
    var errs = document.querySelectorAll(".auth-error");
    for (var i = 0; i < errs.length; i++) { errs[i].hidden = true; errs[i].textContent = ""; }
  }
  function showAuthError(id, msg) {
    var el = document.getElementById(id);
    if (el) { el.textContent = msg; el.hidden = false; }
  }
  function renderGrade() {
    var view = document.getElementById("grade-view");
    if (view) { view.textContent = authGrade + "级"; }
  }

  function doLogin() {
    var nick = (document.getElementById("login-nick").value || "").trim();
    var code = (document.getElementById("login-code").value || "").trim();
    if (!nick || !/^\d{6}$/.test(code)) {
      showAuthError("login-error", "请输入昵称和六位数字传承码");
      return;
    }
    var btn = document.getElementById("login-submit");
    btn.disabled = true; btn.textContent = "正在验证…";
    fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nickname: nick, legacy_code: code })
    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); }).then(function (res) {
      btn.disabled = false; btn.textContent = "进入第五季";
      if (!res.ok) { showAuthError("login-error", res.data.error || "登录失败"); return; }
      saveAuth({ nickname: nick, code: code, user: res.data.user });
      closeAuthModal(true);
      refreshAuthSections();
    }).catch(function () {
      btn.disabled = false; btn.textContent = "进入第五季";
      showAuthError("login-error", "网络异常，请稍后再试");
    });
  }

  function doRegister() {
    var nick = (document.getElementById("reg-nick").value || "").trim();
    var major = (document.getElementById("reg-major").value || "").trim();
    var grade = authGrade + "级";
    if (!nick || !major) { showAuthError("reg-error", "昵称和专业均为必填"); return; }
    var btn = document.getElementById("reg-submit");
    btn.disabled = true; btn.textContent = "正在注册…";
    fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nickname: nick, grade: grade, major: major })
    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); }).then(function (res) {
      btn.disabled = false; btn.textContent = "注册并领取传承码";
      if (!res.ok) { showAuthError("reg-error", res.data.error || "注册失败"); return; }
      var cr = document.getElementById("acr-code");
      if (cr) { cr.textContent = res.data.legacy_code; }
      showAuthPanel("code");
      pendingReg = { nickname: nick, code: res.data.legacy_code, user: res.data.user };
    }).catch(function () {
      btn.disabled = false; btn.textContent = "注册并领取传承码";
      showAuthError("reg-error", "网络异常，请稍后再试");
    });
  }
  var pendingReg = null;

  function finishRegistration() {
    if (pendingReg) { saveAuth(pendingReg); pendingReg = null; }
    closeAuthModal(true);
    refreshAuthSections();
  }

  // 登录态变化后刷新依赖身份的区块（投票已投态/我的种子卡/我的团队）
  function refreshAuthSections() {
    loadDormant();
    loadSeeds();
    loadTeams();
  }

  /* ==================== v10.0 需求③：成员间留言 ==================== */
  var memberMsgModal = document.getElementById("member-msg-modal");
  var memberMsgTarget = null;
  document.addEventListener("click", function (e) {
    var mm = e.target.closest("[data-member-msg]");
    if (mm) {
      memberMsgTarget = mm.getAttribute("data-member-msg");
      var title = document.getElementById("member-msg-title");
      var input = document.getElementById("member-msg-input");
      if (title) { title.textContent = "给 " + memberMsgTarget + " 留言"; }
      if (input) { input.value = ""; }
      if (memberMsgModal) { memberMsgModal.hidden = false; input && input.focus(); }
      return;
    }
    if (e.target.closest("[data-close-member-msg]")) {
      if (memberMsgModal) { memberMsgModal.hidden = true; }
      return;
    }
    var sendMsgBtn = e.target.closest("#member-msg-ok");
    if (sendMsgBtn && memberMsgTarget) {
      var content = ((document.getElementById("member-msg-input") || {}).value || "").trim();
      if (!content) { window.alert("写点想说的吧"); return; }
      sendMsgBtn.disabled = true;
      fetch("/api/messages/send", {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
        body: JSON.stringify({ to: memberMsgTarget, content: content })
      }).then(function (r) { return r.json(); }).then(function (d) {
        sendMsgBtn.disabled = false;
        if (d.success) {
          memberMsgModal.hidden = true;
          window.alert("留言已送入 " + memberMsgTarget + " 的知颜信箱");
        } else { window.alert(d.error || "发送失败"); }
      }).catch(function () { sendMsgBtn.disabled = false; window.alert("发送失败，请重试"); });
    }
  });

  /* v10.0 跳转对话并预填消息 */
  function enterChatWith(preset) {
    if (detailModal) { detailModal.hidden = true; }
    if (teamModal) { teamModal.hidden = true; }
    requireAuth("与知颜对话需要先登录").then(function (ok) {
      if (!ok) { return; }
      showView("chat");
      if (inputEl) { inputEl.value = preset; inputEl.focus(); }
    });
  }

  /* 认证弹窗事件绑定 */
  document.addEventListener("click", function (e) {
    // v8.0 给发起人留言：跳转对话并预填
    var mf = e.target.closest("[data-msg-founder]");
    if (mf) {
      var who = mf.getAttribute("data-msg-founder");
      if (detailModal) { detailModal.hidden = true; }
      requireAuth("给发起人留言需要先登录（留言会投递到 TA 的信箱）").then(function (ok) {
        if (!ok) { return; }
        showView("chat");
        if (inputEl) { inputEl.value = "请帮我给「" + who + "」留言：你好！我对你发起的项目很感兴趣，想进一步了解（帮我润色并补充我的来意）。"; inputEl.focus(); }
      });
      return;
    }
    // v8.0 发起组队
    var ct = e.target.closest("[data-create-team]");
    if (ct) {
      var pid = parseInt(ct.getAttribute("data-create-team"), 10);
      var ptitle = ct.getAttribute("data-team-title") || ("项目#" + pid);
      if (detailModal) { detailModal.hidden = true; }
      requireAuth("发起组队需要先登录").then(function (ok) {
        if (!ok) { return; }
        var name = (prompt("队伍名称（如：" + ptitle.slice(0, 6) + "接力队）：") || "").trim();
        if (!name) { return; }
        var desc = (prompt("招募说明（想找什么样的伙伴、做什么）：") || "").trim();
        fetch("/api/teams", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
          body: JSON.stringify({ name: name, description: desc, project_id: pid })
        }).then(function (r) { return r.json(); }).then(function (d) {
          if (d && d.success) {
            alert("队伍已创建！在组队空间可以管理申请，通过后就能和队友（还有知颜）在协作空间对话了。");
            loadTeams();
            var ts = document.getElementById("teams");
            if (ts) { ts.scrollIntoView({ block: "start", behavior: "smooth" }); }
          } else { alert((d && d.error) || "创建失败"); }
        });
      });
      return;
    }
  });

  document.addEventListener("click", function (e) {
    var t;
    if ((t = e.target.closest("[data-auth-tab]"))) { switchAuthTab(t.getAttribute("data-auth-tab")); return; }
    if (e.target.closest("[data-close-auth]")) { closeAuthModal(null); return; }
    if ((t = e.target.closest("[data-grade]"))) {
      // ▼ 滚向更晚的年份（2025、2026…），▲ 回到更早
      authGrade += (t.getAttribute("data-grade") === "down" ? 1 : -1);
      if (authGrade < 2015) { authGrade = 2015; }
      if (authGrade > 2035) { authGrade = 2035; }
      renderGrade(); return;
    }
    if (e.target.closest("#login-submit")) { doLogin(); return; }
    if (e.target.closest("#reg-submit")) { doRegister(); return; }
    if (e.target.closest("#acr-done")) { finishRegistration(); return; }
    if (e.target.closest("[data-action='open-auth']")) { openAuthModal("凭昵称与专属传承码进入——你的档案、项目与对话记忆都在这里"); return; }
    if (e.target.closest("[data-action='logout']")) {
      saveAuth(null);          // saveAuth 内部已做 v9.0 残留清理（对话历史/气泡/会话线程）
      try { localStorage.removeItem("fs_nick"); } catch (err) {}
      // 关闭所有身份相关弹窗
      ["team-modal", "profile-modal", "story-modal", "group-modal", "leaderboard-modal", "handbook-modal", "recruit-modal"].forEach(function (id) {
        var m = document.getElementById(id); if (m) { m.hidden = true; }
      });
      if (inboxModal) { inboxModal.hidden = true; }
      refreshAuthSections();
      return;
    }
    if (e.target.closest("[data-action='open-inbox']")) { openInbox(); return; }
    if (e.target.closest("[data-close-inbox]")) { closeInbox(); return; }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") { return; }
    if (authModal && !authModal.hidden) {
      if (document.activeElement === document.getElementById("login-nick")) { document.getElementById("login-code").focus(); return; }
      if (document.activeElement === document.getElementById("login-code")) { doLogin(); return; }
      if (document.activeElement === document.getElementById("reg-nick")) { document.getElementById("reg-major").focus(); return; }
      if (document.activeElement === document.getElementById("reg-major")) { doRegister(); return; }
    }
  });

  /* 信箱 */
  var inboxModal = document.getElementById("inbox-modal");
  function openInbox() {
    if (!auth) { return; }
    if (!inboxModal) { return; }
    inboxModal.hidden = false;
    document.body.style.overflow = "hidden";
    var list = document.getElementById("inbox-list");
    if (list) { list.innerHTML = '<p class="inbox-empty">正在取信…</p>'; }
    fetch("/api/messages/inbox", { headers: authHeaders() })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!list) { return; }
        var items = d.messages || [];
        if (!items.length) {
          list.innerHTML = '<p class="inbox-empty">信箱空空的——去和知颜聊聊，让 TA 帮你联系感兴趣的同学吧</p>';
          return;
        }
        var html = "";
        for (var i = 0; i < items.length; i++) {
          var m = items[i];
          html += '<div class="inbox-item">' +
            '<div class="inbox-meta"><b class="inbox-sender">' + escapeHtml(m.sender_nickname || "—") + '</b>' +
            '<span class="inbox-time">' + escapeHtml(formatTime(m.created_at)) + '</span></div>' +
            '<p class="inbox-content">' + escapeHtml(m.content || "") + '</p></div>';
        }
        list.innerHTML = html;
        refreshUnread();
      })
      .catch(function () {
        if (list) { list.innerHTML = '<p class="inbox-empty">信箱加载失败，请稍后再试</p>'; }
      });
  }
  function closeInbox() {
    if (!inboxModal) { return; }
    inboxModal.hidden = true;
    document.body.style.overflow = "";
  }
  function formatTime(iso) {
    if (!iso) { return ""; }
    try {
      var d = new Date(iso);
      var p = function (n) { return (n < 10 ? "0" : "") + n; };
      return (d.getMonth() + 1) + "月" + d.getDate() + "日 " + p(d.getHours()) + ":" + p(d.getMinutes());
    } catch (e) { return ""; }
  }

  function getSessionId() {
    var sid = sessionStorage.getItem(SESSION_KEY);
    if (!sid) {
      sid = "web-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
      sessionStorage.setItem(SESSION_KEY, sid);
    }
    return sid;
  }

  function getHistory() {
    try { return JSON.parse(sessionStorage.getItem(HISTORY_KEY) || "[]"); }
    catch (e) { return []; }
  }
  function saveHistory() {
    try { sessionStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-60))); } catch (e) {}
  }
  function resetSession() {
    sessionStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(HISTORY_KEY);
    history = [];
  }
  var history = getHistory();

  /* ==================== 视图切换 ==================== */
  function showView(name) {
    var isChat = (name === "chat");
    if (introView) { introView.classList.toggle("active", !isChat); }
    if (chatView) { chatView.classList.toggle("active", isChat); }
    try { sessionStorage.setItem(STORE_KEY, name); } catch (e) {}
    if (isChat) {
      redrawHistory();
      scrollBottom();
      loadStatus();
      if (inputEl) { inputEl.focus(); }
    } else {
      loadStats();
      loadLegacySections();
    }
  }

  /* ==================== 数据加载 ==================== */
  /* 统计数字完全来自后端 /api/stats 真实数据库查询，不做任何基数叠加与模拟增长 */
  var lastStats = { users: -1, projects: -1, awakened: -1 };

  function animateCount(el, from, to) {
    if (!el) { return; }
    var start = performance.now();
    var dur = 900;
    function step(now) {
      var p = Math.min(1, (now - start) / dur);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(from + (to - from) * eased);
      if (p < 1) { requestAnimationFrame(step); }
    }
    requestAnimationFrame(step);
  }

  function loadStats() {
    fetch("/api/stats").then(function (r) { return r.json(); }).then(function (d) {
      var users = d.users || 0;
      var projects = d.projects || 0;
      var awakened = d.awakened || 0;
      if (statUsers) { animateCount(statUsers, Math.max(0, lastStats.users), users); }
      if (statProjects) { animateCount(statProjects, Math.max(0, lastStats.projects), projects); }
      if (statAwaken) { animateCount(statAwaken, Math.max(0, lastStats.awakened), awakened); }
      lastStats = { users: users, projects: projects, awakened: awakened };
    }).catch(function () { /* 保持占位 */ });
  }

  /* 每 60 秒静默刷新一次真实数据：数字仅随数据库实际变化而变化 */
  setInterval(loadStats, 60000);

  function loadStatus() {
    fetch("/api/health").then(function (r) { return r.json(); }).then(function (d) {
      var ok = !!(d && d.agent_ready);
      if (statusEl) {
        statusEl.textContent = ok ? "● 在线" : "● 离线";
        statusEl.style.color = ok ? "#3e9e5b" : "#c0564b";
      }
    }).catch(function () {
      if (statusEl) { statusEl.textContent = "● 离线"; statusEl.style.color = "#c0564b"; }
    });
  }

  /* ==================== 传承扩展板块（真实数据驱动） ==================== */
  function lsGet(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key) || "null") || fallback; } catch (e) { return fallback; }
  }
  function lsSet(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }

  var skillsCache = [];
  function loadSkills() {
    var box = document.getElementById("skills-rows");
    if (!box) { return; }
    fetch("/api/skills").then(function (r) { return r.json(); }).then(function (d) {
      var items = (d && d.skills) || [];
      skillsCache = items;
      if (!items.length) {
        box.innerHTML = '<div class="skills-empty">暂无足够档案数据——随着同学建档与项目入库，图谱会逐渐清晰</div>';
        return;
      }
      // v6.2：技能图谱大全——条形图改为技能标签墙，点开看可参与的项目
      var html = '<div class="skill-chips">' + items.map(function (it) {
        var projCount = (it.projects || []).length;
        var cls = it.gap > 0 ? "chip-scarce" : (it.gap < 0 ? "chip-rich" : "chip-even");
        return '<button type="button" class="skill-chip ' + cls + '" data-skill="' + escapeHtml(it.skill) + '">' +
          '<span class="chip-name">' + escapeHtml(it.skill) + '</span>' +
          '<span class="chip-meta">需 ' + it.demand + ' · 供 ' + it.supply + '</span>' +
          (projCount ? '<span class="chip-count">' + projCount + ' 个项目</span>' : '<span class="chip-count chip-count-zero">可发起</span>') +
        '</button>';
      }).join("") + '</div>';
      box.innerHTML = html;
    }).catch(function () {
      box.innerHTML = '<div class="skills-empty">图谱加载失败，稍后自动重试</div>';
    });
  }

  /* ==================== v6.2 项目引入：搜索 + 种子记忆卡 + 引入接棒 ==================== */
  var importInput = document.getElementById("import-input");
  var importBtn = document.getElementById("import-search-btn");
  var importResults = document.getElementById("import-results");

  function renderImportCard(p) {
    var stageName = STAGE_LABELS[p.stage] || p.stage || "—";
    var skills = (p.required_skills || []).slice(0, 3).join(" / ");
    // v7.0 优先级徽标：本校项目 + 有完整交接包
    var badges = "";
    if (p.school === "南京大学") { badges += '<span class="ic-badge ic-school">本校</span>'; }
    if (p.has_handover) { badges += '<span class="ic-badge ic-handover">有交接包</span>'; }
    return '<article class="import-card">' +
      '<div class="import-card-top"><span class="sp-stage">' + stageName + '</span>' +
      (badges ? '<span class="ic-badges">' + badges + '</span>' : '') +
      '<span class="import-founder">发起人 · ' + escapeHtml(p.founder_nickname || "—") + '</span></div>' +
      '<h4 class="import-title" data-proj-id="' + p.id + '">' + escapeHtml(p.title) + '</h4>' +
      '<p class="import-desc">' + escapeHtml((p.summary || "").slice(0, 80)) + '</p>' +
      (skills ? '<p class="import-skills">需要：' + escapeHtml(skills) + '</p>' : '') +
      (p.source_name ? '<p class="import-source">报道：' + escapeHtml(p.source_name) + '</p>' : '') +
      '<div class="import-actions">' +
        '<button type="button" class="import-detail-btn" data-proj-id="' + p.id + '">查看种子卡</button>' +
        '<button type="button" class="import-adopt-btn" data-adopt="' + p.id + '">引入接棒</button>' +
      '</div>' +
    '</article>';
  }

  function runImportSearch() {
    if (!importResults) { return; }
    var q = (importInput && importInput.value || "").trim();
    if (!q) {
      importResults.innerHTML = '<div class="import-hint">输入项目名可直接命中该条项目；输入领域或技能会列出相关的项目，点击卡片查看完整种子记忆卡</div>';
      return;
    }
    importResults.innerHTML = '<div class="import-hint import-loading">正在检索项目库…</div>';
    fetch("/api/projects/search?q=" + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (d) {
      var items = (d && d.items) || [];
      if (d && d.error) {
        importResults.innerHTML = '<div class="import-hint">' + escapeHtml(d.error) + '</div>';
        return;
      }
      if (!items.length) {
        importResults.innerHTML = '<div class="import-hint">没有找到与「' + escapeHtml(q) + '」相关的项目。去对话页找知颜聊聊，把你的新想法立成一颗种子？</div>';
        return;
      }
      importResults.innerHTML = '<div class="import-grid">' + items.map(renderImportCard).join("") + '</div>';
    }).catch(function () {
      importResults.innerHTML = '<div class="import-hint">搜索失败，请稍后再试</div>';
    });
  }

  if (importBtn) { importBtn.addEventListener("click", runImportSearch); }
  if (importInput) {
    importInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); runImportSearch(); }
    });
  }
  document.addEventListener("click", function (e) {
    // 种子卡详情
    var detailTarget = e.target.closest("[data-proj-id]");
    if (detailTarget) {
      openProjectDetail(parseInt(detailTarget.getAttribute("data-proj-id"), 10));
      return;
    }
    // 引入接棒（v7.0：登录身份，不再手输昵称）
    var adoptBtn = e.target.closest("[data-adopt]");
    if (!adoptBtn) { return; }
    var projectId = parseInt(adoptBtn.getAttribute("data-adopt"), 10);
    requireAuth("引入项目需要先登录——接棒人身份将记入项目成员名单").then(function (ok) {
      if (!ok) { return; }
      adoptBtn.disabled = true;
      adoptBtn.textContent = "引入中…";
      fetch("/api/projects/import", {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
        body: JSON.stringify({ project_id: projectId })
      }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); }).then(function (res) {
        if (!res.ok) {
          adoptBtn.disabled = false;
          adoptBtn.textContent = "引入接棒";
          window.alert(res.data.error || "引入失败，请稍后再试");
          return;
        }
        adoptBtn.textContent = res.data.action === "duplicated" ? "✓ 已引入过" : "✓ 已引入我的种子库";
        adoptBtn.classList.add("is-imported");
        openDetail(
          '<div class="fd-head"><span class="fd-icon">🌱</span><h3>已引入「' + escapeHtml(res.data.title || "") + '」</h3>' +
          '<p class="fd-sub">' + escapeHtml((res.data.nickname || (auth && auth.nickname) || "")) + ' · 接棒人身份已记录</p></div>' +
          '<div class="fd-body"><p>这个项目已进入你的种子库。接下来：</p>' +
          '<ul class="sp-list">' +
            '<li><b>1.</b> 到对话页对知颜说「我要接棒 #' + res.data.project_id + '」，她会带你走三步确认流程（意愿 → 原负责人核验授权 → 双方确认唤醒）</li>' +
            '<li><b>2.</b> 接棒后以你的团队名义补充档案与动态——原团队的发起人署名、交接包、贡献记录全部保留</li>' +
            '<li><b>3.</b> 团队记录：该项目现有 ' + (res.data.members || 1) + ' 位成员（含原团队与接棒人）</li>' +
          '</ul></div>' +
          '<div class="fd-try">尊重原团队劳动成果：接棒补充的档案会标注「由接棒团队补充」，原内容只增不删。</div>'
        );
      }).catch(function () {
        adoptBtn.disabled = false;
        adoptBtn.textContent = "引入接棒";
        window.alert("网络异常，引入失败，请稍后再试");
      });
    });
  });

  var dormantGroups = {};
  function renderVoteCard(p) {
    var days = (p.dormant_days === null || p.dormant_days === undefined) ? "—" : p.dormant_days;
    var voted = !!p.voted;
    return '<article class="vote-card">' +
      '<div class="vote-top">' +
        '<span class="vote-days">❄️ 已休眠 ' + days + ' 天</span>' +
        '<span class="vote-count"><b>' + p.votes + '</b> 人想用</span>' +
      '</div>' +
      '<h3 class="vote-title">' + escapeHtml(p.title) + '</h3>' +
      '<p class="vote-desc">' + escapeHtml((p.summary || "").slice(0, 64)) + '</p>' +
      '<div class="vote-meta"><span>发起人 · ' + escapeHtml(p.founder_nickname || "—") + '</span>' +
      (p.required_skills && p.required_skills.length ? '<span class="vote-skills">等一位会 ' + escapeHtml(p.required_skills.slice(0, 3).join(" / ")) + ' 的你</span>' : "") +
      '</div>' +
      '<div class="vote-actions">' +
      '<button class="vote-btn' + (voted ? " is-voted" : "") + '" data-vote="' + p.id + '"' + (voted ? " disabled" : "") + '>' + (voted ? "✓ 已投" : "我也想用") + '</button>' +
      '<button class="vote-view" data-view-seed="' + p.id + '">种子卡</button>' +
      '</div>' +
    '</article>';
  }

  function loadDormant() {
    var grid = document.getElementById("votes-grid");
    if (!grid) { return; }
    fetch("/api/dormant", { headers: authHeaders() }).then(function (r) { return r.json(); }).then(function (d) {
      var items = (d && d.dormant) || [];
      if (!items.length) {
        grid.innerHTML = '<div class="votes-empty">当前没有休眠中的种子。</div>';
        return;
      }
      // v8.0：按项目类型（domain_tags[0]）分类分组，组内按票数降序
      items.sort(function (a, b) { return (b.votes || 0) - (a.votes || 0); });
      var groups = {};
      var order = [];
      items.forEach(function (p) {
        var tags = p.domain_tags || [];
        var key = (tags[0] || "其他方向");
        if (!groups[key]) { groups[key] = []; order.push(key); }
        groups[key].push(p);
      });
      order.sort(function (a, b) {
        var maxA = Math.max.apply(null, groups[a].map(function (p) { return p.votes || 0; }));
        var maxB = Math.max.apply(null, groups[b].map(function (p) { return p.votes || 0; }));
        return maxB - maxA;
      });
      // v7.0：已登录用户直接显示已投态；未登录一律"我也想用"，点击后先登录再计票
      var card = renderVoteCard;
      // v9.0：每个类型仅展示票数最高的 1 个项目，其余在展开弹窗中查看
      dormantGroups = {};
      order.forEach(function (k) {
        dormantGroups[k] = groups[k].slice().sort(function (a, b) { return (b.votes || 0) - (a.votes || 0); });
      });
      grid.innerHTML = order.map(function (k) {
        var list = dormantGroups[k];
        var top = list[0];
        var restN = list.length - 1;
        // v10.0 需求②：展开按钮缩小为小胶囊，嵌在标题行内（不再独占网格一整格）
        return '<div class="votes-group">' +
          '<h4 class="votes-group-title"><span>' + escapeHtml(k) + '</span><i>' + list.length + ' 个休眠项目 · 展示榜首</i>' +
          (restN > 0 ? '<button class="votes-group-more" data-group-open="' + escapeHtml(k) + '" title="展开其余 ' + restN + ' 个项目">展开 +' + restN + '</button>' : "") +
          '</h4>' +
          '<div class="votes-group-grid">' + card(top) + '</div>' +
        '</div>';
      }).join("");
    }).catch(function () {
      grid.innerHTML = '<div class="votes-empty">休眠种子清单加载失败，稍后自动重试</div>';
    });
  }

  function loadStories() {
    var grid = document.getElementById("stories-grid");
    if (!grid) { return; }
    fetch("/api/stories").then(function (r) { return r.json(); }).then(function (d) {
      var items = (d && d.stories) || [];
      if (!items.length) {
        grid.innerHTML = '<div class="stories-empty">故事墙还空着。下一次唤醒接棒会写下第一张故事卡。</div>';
        return;
      }
      var liked = lsGet("fs_liked", []);
      var html = items.map(function (s) {
        // v9.0 档案故事：基于真实报道艺术加工，点开看全文
        if (s.kind === "archive") {
          var atags = (s.tags || []).slice(0, 3).map(function (t) {
            return '<span class="story-hl">✦ ' + escapeHtml(String(t).slice(0, 12)) + '</span>';
          }).join("");
          return '<article class="story-card story-archive-card" data-story-open="' + s.story_id + '">' +
            '<div class="story-top">' +
              (s.is_featured ? '<span class="story-featured">★ 档案精选</span>' : '<span class="story-featured story-featured-plain">📜 档案故事</span>') +
              '<span class="story-days">' + escapeHtml(s.era || "") + '</span>' +
            '</div>' +
            '<h3 class="story-title">' + escapeHtml(s.project_title) + '</h3>' +
            '<p class="story-text">' + escapeHtml((s.summary || "").slice(0, 96)) + '</p>' +
            (atags ? '<div class="story-hls">' + atags + '</div>' : "") +
            '<div class="story-relay story-relay-archive">' +
              '<span class="relay-from">' + escapeHtml(s.school || "—") + '</span>' +
              '<i class="relay-arrow">·</i>' +
              '<span class="relay-to">点开读全文</span>' +
            '</div>' +
            '<span class="story-open-hint">📖 点击卡片展开故事</span>' +
          '</article>';
        }
        var isLiked = liked.indexOf(s.id) >= 0;
        var hl = (s.highlights || []).slice(0, 3).map(function (h) {
          return '<span class="story-hl">✦ ' + escapeHtml(String(h).slice(0, 26)) + '</span>';
        }).join("");
        return '<article class="story-card">' +
          '<div class="story-top">' +
            (s.is_featured ? '<span class="story-featured">★ 精选传承</span>' : "") +
            '<span class="story-days">沉睡 ' + (s.period_days || 0) + ' 天后被唤醒</span>' +
          '</div>' +
          '<h3 class="story-title">' + escapeHtml(s.project_title) + '</h3>' +
          '<p class="story-text">' + escapeHtml(s.story_text || "") + '</p>' +
          (hl ? '<div class="story-hls">' + hl + '</div>' : "") +
          '<div class="story-relay">' +
            '<span class="relay-from">' + escapeHtml(s.founder_nickname) + '</span>' +
            '<i class="relay-arrow">──▶</i>' +
            '<span class="relay-to">' + escapeHtml(s.successor_nickname) + '</span>' +
          '</div>' +
          '<button class="story-like' + (isLiked ? ' is-liked' : '') + '" data-like="' + s.id + '"' + (isLiked ? ' disabled' : '') + '>' +
            '<i>♥</i> <b>' + (s.likes || 0) + '</b>' +
          '</button>' +
        '</article>';
      }).join("");
      grid.innerHTML = html;
    }).catch(function () {
      grid.innerHTML = '<div class="stories-empty">故事墙加载失败，稍后自动重试</div>';
    });
  }

  function loadLeaderboard() {
    var strip = document.getElementById("leaderboard-strip");
    var list = document.getElementById("lb-list");
    if (!strip || !list) { return; }
    fetch("/api/leaderboard").then(function (r) { return r.json(); }).then(function (d) {
      var items = (d && d.leaderboard) || [];
      if (!items.length) { strip.hidden = true; return; }
      var medals = ["🥇", "🥈", "🥉", "4.", "5."];
      list.innerHTML = items.map(function (u, i) {
        return '<span class="lb-item"><b class="lb-rank">' + medals[i] + '</b>' +
          escapeHtml(u.nickname) + '<i class="lb-pts">' + u.points + ' 分</i></span>';
      }).join("");
      strip.hidden = false;
    }).catch(function () { strip.hidden = true; });
  }

  // v9.0 风云榜完整版：全量排名 + 积分规则 + 画像查看
  function openLeaderboardModal() {
    var mask = document.getElementById("leaderboard-modal");
    var body = document.getElementById("lb-list-full");
    var rules = document.getElementById("lb-rules");
    if (!mask || !body) { return; }
    mask.hidden = false;
    if (rules) {
      rules.innerHTML = '<div class="lb-loading">积分规则加载中…</div>';
    }
    body.innerHTML = '<div class="lb-loading">正在翻开风云榜……</div>';
    fetch("/api/leaderboard?full=1").then(function (r) { return r.json(); }).then(function (d) {
      var items = (d && d.leaderboard) || [];
      if (!items.length) {
        body.innerHTML = '<div class="lb-loading">还没有传承者上榜——第一棒就从你开始。</div>';
        return;
      }
      var medals = ["🥇", "🥈", "🥉"];
      var rows = items.map(function (u, i) {
        var rank = i < 3 ? medals[i] : '<span class="lb-rank-plain">' + (i + 1) + '</span>';
        var badge = u.profile_public
          ? '<button class="lb-view-profile" data-lb-profile="' + escapeHtml(u.nickname) + '">看画像</button>'
          : '<span class="lb-priv">画像未公开</span>';
        return '<li class="lb-row' + (i < 3 ? ' lb-row-top' : '') + '">' +
          '<span class="lb-rank-cell">' + rank + '</span>' +
          '<span class="lb-name">' + escapeHtml(u.nickname) +
            '<i class="lb-meta">' + escapeHtml(u.grade || "") + (u.major ? " · " + escapeHtml(u.major) : "") + '</i></span>' +
          '<span class="lb-breakdown">' + escapeHtml(u.breakdown || "") + '</span>' +
          '<span class="lb-pts-cell">' + u.points + '<i>分</i></span>' +
          badge +
        '</li>';
      }).join("");
      var me = auth ? auth.nickname : null;
      var meRow = me ? '<p class="lb-me">当前登录：' + escapeHtml(me) + ' · 可在下方积分规则里找到自己的得分方式</p>' : "";
      body.innerHTML = meRow +
        '<ol class="lb-full-list">' + rows + '</ol>';
      // 积分规则（后端严格规定的 13 项标准，与计算引擎完全一致）
      if (rules && d.rules) {
        rules.innerHTML = '<h4>积分规则（严格规定 · 系统按数据库真实记录自动计算）</h4>' +
          '<ul class="lb-rules-list">' + d.rules.map(function (r) {
            return '<li><b>' + escapeHtml(r.points) + ' 分</b> ' + escapeHtml(r.label) + '：' + escapeHtml(r.desc) + '</li>';
          }).join("") +
          '<li><b>公开画像</b>：用户在「个人画像」中开启公开展示后，才可在榜单点开查看</li>' +
          '<li><b>并列排序</b>：积分相同时按贡献值高者在前</li></ul>';
      }
    }).catch(function () {
      body.innerHTML = '<div class="lb-loading">风云榜加载失败，稍后再试</div>';
    });
  }

  function closeLeaderboardModal() {
    var mask = document.getElementById("leaderboard-modal");
    if (mask) { mask.hidden = true; }
  }

  // v9.0 功能手册：完整分点介绍（覆盖全部功能）
  var HANDBOOK_HTML =
    '<div class="hb-hero">' +
      '<h3>「第五季·续种」功能手册</h3>' +
      '<p>一个项目的离开，不该是一段记忆的终点。本手册把校园里所有可用的传承功能逐一拆解，按「使用频率」与「成长路径」编排——你可以从头读到尾，也可以按需跳转。</p>' +
    '</div>' +
    '<section class="hb-sec">' +
      '<h4>一 · 身份与档案</h4>' +
      '<ol>' +
        '<li><b>注册建档</b>：点击右上角「进入/注册」，输入昵称即可建档；系统自动发放一张<b>六位专属传承码</b>（如 441843-008），它是你在本站的唯一钥匙，请妥善保存。</li>' +
        '<li><b>登录</b>：凭「昵称 + 传承码」进入，你的档案、种子卡、项目库、团队与对话记忆都会回到原处。</li>' +
        '<li><b>本地多用户隔离</b>：本站支持同一台设备上多人先后使用；切换或退出账号时，对话气泡、留言、团队面板等残留信息会被自动清空，看不到彼此的隐私。</li>' +
        '<li><b>个人画像</b>：在「个人画像」中完善年级、专业、兴趣与传承愿景；可自行选择<b>是否公开展示</b>——公开后，他人可在风云榜点开查看你的画像。</li>' +
      '</ol>' +
    '</section>' +
    '<section class="hb-sec">' +
      '<h4>二 · 与 Agent「知颜」对话</h4>' +
      '<ol>' +
        '<li><b>首话与引路</b>：新用户进入后，知颜会先用一段「首话」带你认识站点；随时可在对话里提问。</li>' +
        '<li><b>传承码找回</b>：忘记传承码时，直接告诉知颜自己的昵称与基本信息，核实后会提示你的传承码。</li>' +
        '<li><b>上传文件</b>：对话输入框旁的「上传」按钮支持交接文档、活动照片等附件（单文件 ≤5MB），文件会进入你的项目档案。</li>' +
        '<li><b>搜索引入</b>：对话里说「帮我搜一下××」即可联网检索公开资料，检索结果可直接转成公开种子卡或项目素材。</li>' +
        '<li><b>获取交接包（v10 新）</b>：对知颜说「获取 FS-017 的交接包」或「我想看 PJ-003 的交接包」，她会按编号取出<b>已获授权公开</b>的交接包；未公开的会如实告知需要主人授权。</li>' +
      '</ol>' +
    '</section>' +
    '<section class="hb-sec">' +
      '<h4>三 · 种子库体系（三件套）</h4>' +
      '<ol>' +
        '<li><b>个人种子卡</b>：存放你自己的零碎灵感（编号=传承码-序号，仅你可见）。<b>点开任意一张卡即可查看</b>灵感原文、标签与状态，还能一键「和知颜聊聊这个灵感」让它长成项目。</li>' +
        '<li><b>引入的公开种子卡</b>：在公开种子卡详情点「🌱 引入我的种子库」即可收进你的库；引入的卡<b>可随时移除</b>（点「移除」即可，不影响项目与其他成员）。</li>' +
        '<li><b>公开种子库</b>：所有公开项目档案（FS-#N）+ 他人公开交接包的个人项目（PJ-#N）一览。支持<b>折叠/展开</b>（默认只显示前 6 张）。卡片角标记了交接包状态：「📦 交接包可获取」或「📦 交接包需授权」——存量公开种子卡的交接包已全部开放；之后用户新上传的种子卡需<b>项目主人授权</b>后才能获取。</li>' +
        '<li><b>导入种子代码</b>：拿到他人分享的种子码（如 FS-001），在种子库点「导入种子代码」输入即可把那张卡接进你的库。</li>' +
        '<li><b>休眠种子候选池</b>：需求投票区按类型聚类展示——每个类型默认只展示 1 个最热项目，标题行右侧有<b>「展开 +N」小按钮</b>，点开可在弹窗查看同类型全部候选并投票（「我也想用」），票数决定唤醒优先级。</li>' +
      '</ol>' +
    '</section>' +
    '<section class="hb-sec">' +
      '<h4>四 · 个人项目库（v10 新 · 交接包统一管理）</h4>' +
      '<ol>' +
        '<li><b>是什么</b>：种子库的第三个标签页「📁 我的项目库」。它与种子卡不同——存放你自己的<b>完整项目档案</b>（编号 PJ-#N，仅你可见），可以是未完成的想法、正在接棒的项目或已完成的成果。</li>' +
        '<li><b>建档方式</b>：点「＋ 新建项目档案」填表，或直接对知颜说「帮我在项目库里记录一个新项目」；每个档案包含名称、简介、状态（进行中/未完成/接棒中/已完成）、标签与完整详情。</li>' +
        '<li><b>让知颜生成交接包</b>：点项目卡上的「📦 生成交接包」，或对知颜说「帮我把 PJ-001 生成交接包」——她会先读项目完整档案，再提炼<b>五段式清单</b>（已有成果/执行经验/踩过的坑/遗留问题/可复用资源）与三项治理声明（授权范围/资源有效期/原团队权益）。</li>' +
        '<li><b>公开授权</b>：生成交接包后，点「🌍 公开交接包」开关（或对知颜说「把 PJ-001 的交接包公开」）。公开后，其他人可以在<b>公开种子库</b>看到它（PJ-#N 卡），也可在与知颜对话中凭编号获取；取消公开即刻下架。</li>' +
        '<li><b>统一管理</b>：你的所有交接包与项目信息都在项目库一处管理——查看、重制、公开、删除均在项目卡上一键完成。</li>' +
      '</ol>' +
    '</section>' +
    '<section class="hb-sec">' +
      '<h4>五 · 项目传承链路</h4>' +
      '<ol>' +
        '<li><b>唤醒接棒</b>：在候选池或公开卡详情中点「唤醒接棒」，生成唤醒记录，项目由你续写。</li>' +
        '<li><b>交接包</b>：老成员可沉淀「交接包」（项目全档案），接棒者据此快速上手；沉淀交接包计入积分。获取规则见「四 · 个人项目库」与「三 · 种子库体系」的授权说明。</li>' +
        '<li><b>项目阶段</b>：项目从休眠 → 唤醒 → 运转 → 完成·传承中，阶段推进全程留痕。</li>' +
        '<li><b>留言信箱</b>：在项目卡或画像里给发起人留言，消息进入对方信箱，实现跨届牵线。</li>' +
      '</ol>' +
    '</section>' +
    '<section class="hb-sec">' +
      '<h4>六 · 组队空间</h4>' +
      '<ol>' +
        '<li><b>发布招募</b>：点「发布招募」上传招募海报（≤2.5MB）并填写队名与说明，海报对全校可见。</li>' +
        '<li><b>海报自适应与放大（v10 新）</b>：招募区的海报自动适配卡片宽度；<b>点击海报即可放大查看</b>（弹窗灯箱，点空白处或 × 关闭），团队详情里的海报同样支持。</li>' +
        '<li><b>招募详情（v10 新）</b>：点「详情」进入团队空间，可以看到<b>项目现状</b>（关联项目的阶段、简介、领域与所需能力）与<b>全部成员</b>。</li>' +
        '<li><b>共享知颜记忆（v10 新）</b>：团队协作空间里，队长和组员与<b>同一份知颜记忆</b>对话；全队的对话记录<b>互相可见</b>——谁问过什么、知颜答过什么，后来的人打开就能看到完整上下文。</li>' +
        '<li><b>成员间留言（v10 新）</b>：成员列表中每个成员旁有「✉ 留言」按钮，点开即可给 TA 递话，留言直达对方的知颜信箱。</li>' +
        '<li><b>申请加入</b>：在招募区点「申请加入」，队长的团队空间会收到申请，确认后即组队成功。</li>' +
      '</ol>' +
    '</section>' +
    '<section class="hb-sec">' +
      '<h4>七 · 传承故事与档案</h4>' +
      '<ol>' +
        '<li><b>传承故事墙</b>：收录档案故事与真实唤醒实录，卡片点开即可<b>阅读全文</b>（在事实基础上做了少量文学润色）。</li>' +
        '<li><b>种子档案墙</b>：按届陈列历季项目档案；「展开传承故事」按钮位于「南大传承实录」上方，点开可纵览全部档案故事。</li>' +
      '</ol>' +
    '</section>' +
    '<section class="hb-sec">' +
      '<h4>八 · 传承者风云榜</h4>' +
      '<ol>' +
        '<li><b>完整榜单</b>：点风云榜条目上的「完整榜单与积分规则」可打开全量榜单（前 50 名），实时更新。</li>' +
        '<li><b>积分标准（严格规定）</b>：建档 +5；唤醒接棒 +30/次；双料传承人（接棒 ≥2）+50；发起项目 +10/个；多产发起人（≥3 个）+30；沉淀交接包 +15/个；项目完成传承 +40；为种子投票 +5/票；投票召集人（≥5 票）+20；存个人种子卡 +5/张；引入公开种子卡 +15/个；团队组建成功 +20/支；留言牵线 +2/条（封顶 20 分）。全部由系统按真实记录自动计算。</li>' +
        '<li><b>画像查看</b>：榜单中已公开画像的用户可点「看画像」查看其年级、专业与传承足迹；未公开则显示「画像未公开」。</li>' +
      '</ol>' +
    '</section>' +
    '<section class="hb-sec">' +
      '<h4>九 · 知颜对话模拟（照着说就能用）</h4>' +
      '<p class="hb-note">下面是一组真实可用的对话示例。你不需要记指令格式——像和学姐聊天一样说人话，知颜就能办对事。</p>' +
      '<div class="hb-chat">' +
        '<div class="hb-dialog">' +
          '<div class="hb-u">「我是大一新生，会一点 Python，想做点有意思的事」</div>' +
          '<div class="hb-a">知颜会：先为你的能力做<b>需求推理</b>（能力盘点 → 校园需求映射 → 匹配推荐），列出三条适合你的路——比如「技能图谱里正好缺会编程的公益项目」，而不是甩一堆清单。</div>' +
        '</div>' +
        '<div class="hb-dialog">' +
          '<div class="hb-u">「我有个想法：宿舍楼下搞一个共享雨伞角」</div>' +
          '<div class="hb-a">知颜会：把碎片想法提炼成<b>个人种子卡</b>存入你的种子库（编号=传承码-序号，仅你可见），并分析可行性、给出第一步。</div>' +
        '</div>' +
        '<div class="hb-dialog">' +
          '<div class="hb-u">「帮我在项目库里记录一个新项目：食堂菜谱共创，目前调研到一半」</div>' +
          '<div class="hb-a">知颜会：在<b>个人项目库</b>建档（PJ-#N，仅你可见），记录目标、进展与状态（未完成），随时可继续更新。</div>' +
        '</div>' +
        '<div class="hb-dialog">' +
          '<div class="hb-u">「帮我把 PJ-001 生成交接包，我下学期去交换了」</div>' +
          '<div class="hb-a">知颜会：先读这个项目的完整档案，再提炼<b>五段式交接包</b>（成果/经验/坑/遗留问题/可复用资源）与治理声明，存进你的项目库；问她「把它公开」，就能让下一届接棒人获取。</div>' +
        '</div>' +
        '<div class="hb-dialog">' +
          '<div class="hb-u">「获取 FS-017 的交接包」</div>' +
          '<div class="hb-a">知颜会：按编号取出该公开种子卡的交接包给你（若未获主人授权，她会如实说明并建议你联系发起人）。</div>' +
        '</div>' +
        '<div class="hb-dialog">' +
          '<div class="hb-u">「我想唤醒 #17 这个项目」</div>' +
          '<div class="hb-a">知颜会：先让你看清<b>前两任都卡在哪</b>（交接包里的坑与遗留问题），再生成唤醒记录、把你记为接棒人，并给出接手第一周该做的事。</div>' +
        '</div>' +
        '<div class="hb-dialog">' +
          '<div class="hb-u">「帮我找会做海报的同学」</div>' +
          '<div class="hb-a">知颜会：查<b>技能图谱</b>找到标签匹配的同学，评估互补度后帮你给对方信箱<b>留言牵线</b>。</div>' +
        '</div>' +
      '</div>' +
    '</section>' +
    '<section class="hb-sec">' +
      '<h4>十 · 新手引导</h4>' +
      '<ol>' +
        '<li><b>新手教程</b>：首屏的教程聚光灯会分步指引界面各区域（含知颜对话模拟示例）；「跳过」后可从导航栏重新打开。</li>' +
        '<li><b>建议路线</b>：注册建档 → 和知颜聊一次（试试上面第九节的对话）→ 给候选池投票 → 引入一张公开种子卡 → 在项目库建第一个项目档案 → 尝试唤醒接棒或发布招募——六步走完，你就完成了第一次完整的传承闭环。</li>' +
      '</ol>' +
    '</section>';

  function loadEvidence() {
    var source = document.getElementById("evidence-source");
    fetch("/api/evidence").then(function (r) { return r.json(); }).then(function (d) {
      var op = d.operational || {};
      var set = function (id, value) {
        var el = document.getElementById(id);
        if (el) { el.textContent = value; }
      };
      set("ev-projects", op.projects == null ? "—" : op.projects);
      set("ev-coverage", op.handover_coverage_pct == null ? "—" : op.handover_coverage_pct + "%");
      set("ev-awaken", op.awaken_records == null ? "—" : op.awaken_records);
      set("ev-stories", op.story_records == null ? "—" : op.story_records);
      set("pilot-status", (d.pilot && d.pilot.status) || "试点数据加载中");
      if (source) { source.textContent = d.source || "数据来源未返回"; }
      var targets = document.getElementById("pilot-targets");
      if (targets && d.pilot && Array.isArray(d.pilot.targets)) {
        targets.innerHTML = d.pilot.targets.map(function (x) {
          return "<li>" + escapeHtml(String(x)) + "</li>";
        }).join("");
      }
      var casesBox = document.getElementById("pilot-cases");
      if (casesBox && d.pilot && Array.isArray(d.pilot.cases)) {
        casesBox.innerHTML = d.pilot.cases.map(function (c) {
          var s = c.successor || {};
          var r = c.readiness || {};
          var score = c.match_score == null ? "—" : Math.round(c.match_score);
          return '<div class="pilot-case">' +
            '<div class="pc-title">' + escapeHtml(String(c.project_title || ("项目" + c.project_id))) +
              '<span class="pc-stage">' + escapeHtml(String(c.stage_now === "fifth" ? "已重生·第五季" : c.stage_now)) + '</span></div>' +
            '<div class="pc-row"><span class="pc-k">接棒人</span>' +
              escapeHtml(String(s.nickname || "—")) + ' · ' + escapeHtml(String(s.grade || "年级未填")) + ' · ' + escapeHtml(String(s.major || "")) + '</div>' +
            '<div class="pc-row"><span class="pc-k">六维匹配</span><b class="pc-score">' + score + '</b>/100 · ' +
              '交接准备度 <b class="pc-score">' + (r.score == null ? "—" : r.score) + '</b>/100（' + escapeHtml(String(r.level || "未评估")) + '）</div>' +
            '<div class="pc-row"><span class="pc-k">唤醒票</span>' + escapeHtml(String(c.awaken_votes || 0)) + ' 票 · ' +
              escapeHtml(String((c.awakened_at || "").slice(0, 10))) + ' 完成唤醒</div>' +
            '<div class="pc-reason">' + escapeHtml(String(c.match_reason_excerpt || "")) + '</div>' +
          '</div>';
        }).join("");
      }
    }).catch(function () {
      if (source) { source.textContent = "数据库暂不可用 · 不展示未经核验的数据"; }
    });
  }

  // 交接包实探：列表 + 详情原文直读
  function parseMaybeJson(v) {
    if (Array.isArray(v)) { return v; }
    if (typeof v === "string") {
      try { return JSON.parse(v); } catch (e) { return []; }
    }
    return [];
  }

  function loadHandover() {
    var listBox = document.getElementById("handover-list");
    var detailBox = document.getElementById("handover-detail");
    if (!listBox || !detailBox) { return; }
    fetch("/api/handover").then(function (r) { return r.json(); }).then(function (d) {
      if (!d.success || !Array.isArray(d.handovers) || !d.handovers.length) {
        listBox.innerHTML = '<div class="handover-empty">暂无交接包</div>';
        return;
      }
      listBox.innerHTML = d.handovers.map(function (h) {
        var sec = h.sections || {};
        var total = (sec.achievements || 0) + (sec.experience || 0) + (sec.pitfalls || 0) +
                    (sec.remaining_issues || 0) + (sec.reusable_resources || 0);
        return '<button class="ho-item" data-ho="' + h.project_id + '">' +
          '<span class="ho-title">' + escapeHtml(String(h.project_title)) + '</span>' +
          '<span class="ho-meta">' + total + ' 条 · ' + escapeHtml(String(h.stage === "fifth" ? "已续种" : h.stage === "winter" ? "休眠中" : h.stage)) + '</span>' +
        '</button>';
      }).join("");
      listBox.querySelectorAll("[data-ho]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          listBox.querySelectorAll(".ho-item").forEach(function (b) { b.classList.remove("active"); });
          btn.classList.add("active");
          detailBox.innerHTML = '<div class="handover-detail-empty">正在读取交接包全文…</div>';
          fetch("/api/handover?project_id=" + btn.getAttribute("data-ho"))
            .then(function (r) { return r.json(); })
            .then(function (dd) { renderHandoverDetail(dd); })
            .catch(function () {
              detailBox.innerHTML = '<div class="handover-detail-empty">交接包读取失败，请稍后再试</div>';
            });
        });
      });
    }).catch(function () {
      listBox.innerHTML = '<div class="handover-empty">交接包清单读取失败</div>';
    });
  }

  function renderHandoverDetail(d) {
    var detailBox = document.getElementById("handover-detail");
    if (!detailBox) { return; }
    if (!d.success || !d.handover) {
      detailBox.innerHTML = '<div class="handover-detail-empty">' + escapeHtml(String(d.message || "暂无交接包")) + '</div>';
      return;
    }
    var h = d.handover;
    var r = d.readiness || {};
    var gov = parseMaybeJson(h.reusable_resources).filter(function (x) {
      return String(x).indexOf("【") >= 0;
    });
    var res = parseMaybeJson(h.reusable_resources).filter(function (x) {
      return String(x).indexOf("【") < 0;
    });
    var section = function (title, items) {
      var arr = parseMaybeJson(items);
      if (!arr.length) { return ""; }
      return '<div class="ho-sec"><h4>' + title + '（' + arr.length + '）</h4><ul>' +
        arr.map(function (x) { return "<li>" + escapeHtml(String(x)) + "</li>"; }).join("") +
        "</ul></div>";
    };
    detailBox.innerHTML =
      '<h3>' + escapeHtml(String(h.project_id ? "项目 " + h.project_id + " 交接包" : "交接包")) + '</h3>' +
      '<div class="ho-readiness">接续准备度 <b>' + (r.score == null ? "—" : r.score) + '</b>/100 · ' +
        escapeHtml(String(r.level || "未评估")) + ' · 过程动态 ' + escapeHtml(String(d.update_count || 0)) + ' 条</div>' +
      '<div class="ho-scroll">' +
      section("已达成成果", h.achievements) +
      section("运营经验", h.experience) +
      section("踩坑记录", h.pitfalls) +
      section("待办与未尽事项", h.remaining_issues) +
      section("可复用资源", res) +
      section("治理三声明（授权 / 有效期 / 原团队权益）", gov) +
      "</div>";
  }

  var legacyLoaded = false;
  function loadLegacySections() {
    if (legacyLoaded) { return; }
    legacyLoaded = true;
    loadSkills();
    loadDormant();
    loadStories();
    loadLeaderboard();
    loadEvidence();
    loadHandover();
    loadSeeds();
    loadTeams();
  }

  // 需求投票（v7.0：登录后按登录身份计票，未登录先弹认证层）
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-vote]");
    if (!btn || btn.disabled) { return; }
    var projectId = parseInt(btn.getAttribute("data-vote"), 10);
    requireAuth("投票需要先登录——一人一票，票数按账号分开统计").then(function (ok) {
      if (!ok) { return; }
      btn.disabled = true;
      btn.textContent = "投票中…";
      fetch("/api/votes", {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
        body: JSON.stringify({ project_id: projectId })
      }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); }).then(function (res) {
        if (!res.ok) {
          btn.disabled = false;
          btn.textContent = "我也想用";
          window.alert(res.data.error || "投票失败，请稍后再试");
          return;
        }
        btn.classList.add("is-voted");
        btn.textContent = res.data.action === "duplicated" ? "✓ 已投过" : "✓ 已投";
        var card = btn.closest(".vote-card");
        if (card) {
          var cnt = card.querySelector(".vote-count b");
          if (cnt) { cnt.textContent = res.data.votes; }
        }
      }).catch(function () {
        btn.disabled = false;
        btn.textContent = "我也想用";
        window.alert("网络异常，投票失败，请稍后再试");
      });
    });
  });

  // 故事点赞
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-like]");
    if (!btn || btn.disabled) { return; }
    var storyId = parseInt(btn.getAttribute("data-like"), 10);
    fetch("/api/stories/" + storyId + "/like", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (typeof d.likes !== "number") { return; }
        var liked = lsGet("fs_liked", []);
        if (liked.indexOf(storyId) < 0) { liked.push(storyId); }
        lsSet("fs_liked", liked);
        btn.classList.add("is-liked");
        btn.disabled = true;
        var num = btn.querySelector("b");
        if (num) { num.textContent = d.likes; }
      }).catch(function () { /* 静默 */ });
  });

  // 功能全景弹窗
  var featureModal = document.getElementById("feature-modal");
  function openFeatureModal() {
    if (!featureModal) { return; }
    featureModal.hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeFeatureModal() {
    if (!featureModal) { return; }
    featureModal.hidden = true;
    document.body.style.overflow = "";
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-action='open-features']")) { openFeatureModal(); e.preventDefault(); return; }
    if (e.target.closest("[data-close-feature]")) { closeFeatureModal(); }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && featureModal && !featureModal.hidden) { closeFeatureModal(); }
  });

  /* ==================== Markdown 简易渲染 ==================== */
  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function inline(text) {
    return escapeHtml(text)
      .replace(/!\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g, '<img class="md-img" src="$2" alt="$1" loading="lazy"/>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+?\.(?:png|jpe?g|webp|gif))\)/g, '<a class="media-card" href="$2" target="_blank" rel="noopener noreferrer"><img class="mc-thumb" src="$2" alt="$1" loading="lazy"/><span class="mc-info"><span class="mc-title">$1</span><span class="mc-sub">点击查看 · 已存入对象存储</span></span><i class="mc-action">↗</i></a>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a class="md-link" href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`(.+?)`/g, "<code>$1</code>");
  }

  function renderMarkdown(raw) {
    var lines = String(raw).split("\n");
    var html = [];
    var inList = false;
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      var listMatch = line.match(/^\s*(?:[-*•]|\d+[\.、])\s+(.*)$/);
      if (listMatch) {
        if (!inList) { html.push("<ul>"); inList = true; }
        html.push("<li>" + inline(listMatch[1]) + "</li>");
        continue;
      }
      if (inList) { html.push("</ul>"); inList = false; }
      var h = line.match(/^(#{1,4})\s+(.*)$/);
      if (h) { html.push("<h" + (h[1].length + 2) + ">" + inline(h[2]) + "</h" + (h[1].length + 2) + ">"); continue; }
      if (line.trim() === "") { continue; }
      html.push("<p>" + inline(line) + "</p>");
    }
    if (inList) { html.push("</ul>"); }
    return html.join("");
  }

  /* ==================== 对话渲染 ==================== */
  function scrollBottom() {
    if (chatBox) { chatBox.scrollTop = chatBox.scrollHeight; }
  }

  function addBubble(role) {
    var wrap = document.createElement("div");
    wrap.className = "bubble-row " + (role === "user" ? "user-row" : "bot-row");
    var avatar = document.createElement("div");
    avatar.className = "avatar " + (role === "user" ? "avatar-user" : "avatar-bot");
    if (role === "user") {
      avatar.textContent = "我";
    } else {
      var img = document.createElement("img");
      img.src = "static/avatar_zhiyan.png";
      img.alt = "知颜";
      img.className = "avatar-img";
      img.onerror = function () { img.remove(); avatar.textContent = "知"; };
      avatar.appendChild(img);
    }
    var bubble = document.createElement("div");
    bubble.className = "bubble " + (role === "user" ? "bubble-user" : "bubble-bot");
    wrap.appendChild(avatar);
    wrap.appendChild(bubble);
    chatBox.appendChild(wrap);
    return bubble;
  }

  function renderPending(label) {
    return '<span class="typing"><span></span><span></span><span></span></span>' +
      (label ? '<span class="tool-status">' + escapeHtml(label) + '</span>' : "");
  }

  function showTyping() {
    var bubble = addBubble("bot");
    bubble.innerHTML = renderPending("");
    return bubble;
  }

  function setBusy(state) {
    if (sendBtn) { sendBtn.disabled = state; sendBtn.textContent = state ? "回复中…" : "发送"; }
    if (inputEl) { inputEl.disabled = state; }
  }

  var WELCOME_MD = (
    "### 我已经认出你了\n\n" +
    "你的档案、项目与我们的对话记忆都随账号保存——**换个设备、隔几周再来，我们都可以接着聊**。\n\n" +
    "可以直接说：*「帮我看看有啥适合我的项目」*、*「我想给 XX 前辈留言」*，或者补充你的技能与兴趣标签。没有完全匹配时，我也会继续找相邻方向，不会只回一句“没有相关项目”。"
  );

  function addStarterPanel() {
    if (!chatBox) { return; }
    var panel = document.createElement("div");
    panel.className = "chat-starters";
    panel.innerHTML =
      '<p class="starter-title">你可以从这里开始</p>' +
      '<div class="starter-grid">' +
        '<button class="chip starter-card" data-msg="帮我看看有啥适合我的项目，顺便盘点一下我的能力标签。"><b>01 · 找适合我的项目</b><span>能力盘点 → 匹配推荐 → 联系前辈</span></button>' +
        '<button class="chip starter-card" data-msg="我有一个校园项目想法，帮我梳理目标、受益人、实施路径和所需伙伴，先给我看种子卡预览。"><b>02 · 把想法变成项目</b><span>澄清需求 → 种子卡 → 同类案例</span></button>' +
        '<button class="chip starter-card" data-msg="我快毕业了，手上的项目还没做完，帮我整理已有成果、踩坑、遗留问题和可复用资源，准备一份交接包。"><b>03 · 把项目交给下一届</b><span>复盘 → 交接包 → 休眠等待接棒</span></button>' +
        '<button class="chip starter-card" data-msg="帮我看看信箱里有没有新留言。"><b>04 · 我的信箱</b><span>收留言 → 回复联系 → 匹配接洽</span></button>' +
      '</div>';
    chatBox.appendChild(panel);
  }

  function redrawHistory() {
    history = getHistory();
    if (chatBox) { chatBox.innerHTML = ""; }
    for (var i = 0; i < history.length; i++) {
      var b = addBubble(history[i].role);
      b.innerHTML = history[i].role === "user"
        ? escapeHtml(history[i].text)
        : renderMarkdown(history[i].text);
    }
    if (history.length === 0) {
      var b0 = addBubble("bot");
      b0.innerHTML = renderMarkdown(WELCOME_MD);
      addStarterPanel();
    }
  }

  /* ==================== SSE 流式对话 ==================== */
  function streamChat(message, onDelta, onDone, onError, onTool) {
    fetch("/api/chat", {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
      body: JSON.stringify({ message: message, session_id: getSessionId() })
    }).then(function (resp) {
      if (resp.status === 401) {
        // 登录态失效：弹出认证层，登录成功后可重发
        return resp.json().catch(function () { return {}; }).then(function (d) {
          var msg = (d && d.error) ? d.error : "请先登录后再与知颜对话";
          throw { needAuth: true, message: msg };
        });
      }
      if (!resp.ok || !resp.body) {
        return resp.text().then(function (t) {
          throw new Error("HTTP " + resp.status + " " + t.slice(0, 200));
        });
      }
      var reader = resp.body.getReader();
      var decoder = new TextDecoder("utf-8");
      var buffer = "";

      function pump() {
        return reader.read().then(function (result) {
          if (result.done) { onDone(); return; }
          buffer += decoder.decode(result.value, { stream: true });
          var parts = buffer.split("\n\n");
          buffer = parts.pop() || "";
          for (var i = 0; i < parts.length; i++) {
            var seg = parts[i];
            if (seg.indexOf("data:") !== 0) { continue; }
            var payload = seg.slice(5).trim();
            if (!payload) { continue; }
            var evt;
            try { evt = JSON.parse(payload); }
            catch (e) { continue; }
            if (evt.type === "delta" && typeof evt.text === "string") { onDelta(evt.text); }
            else if (evt.type === "tool") { if (onTool) { onTool(evt.label || "正在处理…"); } }
            else if (evt.type === "done") { onDone(); return; }
            else if (evt.type === "error") { onError(evt.message || "stream error"); return; }
          }
          return pump();
        });
      }
      return pump();
    }).catch(function (err) {
      if (err && err.needAuth) {
        if (finished) { return; }
        finished = true;
        botBubble.classList.remove("streaming");
        botBubble.innerHTML = renderMarkdown("🔒 " + err.message);
        setBusy(false);
        requireAuth(err.message).then(function (ok) {
          if (ok) { send(message); }  // 登录成功自动重发
        });
        return;
      }
      onError(String(err && err.message ? err.message : err));
    });
  }

  function send(message) {
    if (!message || !message.trim() || sendBtn.disabled) { return; }
    var userBubble = addBubble("user");
    userBubble.textContent = message;
    history.push({ role: "user", text: message });
    saveHistory();
    if (inputEl) { inputEl.value = ""; inputEl.style.height = "auto"; }
    scrollBottom();
    setBusy(true);

    var botBubble = showTyping();
    scrollBottom();
    var collected = "";
    var finished = false;

    streamChat(message,
      function (delta) {
        collected += delta;
        botBubble.classList.add("streaming");
        botBubble.innerHTML = renderMarkdown(collected);
        scrollBottom();
      },
      function () {
        if (finished) { return; }
        finished = true;
        botBubble.classList.remove("streaming");
        if (!collected) { collected = "（本次没有返回内容，请重试）"; }
        botBubble.innerHTML = renderMarkdown(collected);
        history.push({ role: "bot", text: collected });
        saveHistory();
        setBusy(false);
        scrollBottom();
      },
      function (errMsg) {
        if (finished) { return; }
        finished = true;
        botBubble.classList.remove("streaming");
        botBubble.innerHTML = renderMarkdown("⚠️ 出错了：" + errMsg.slice(0, 300));
        setBusy(false);
        scrollBottom();
      },
      function (label) {
        // 工具执行进度：仅在还没吐出正文时显示，避免覆盖已经流式渲染的内容
        if (finished || collected) { return; }
        botBubble.innerHTML = renderPending(label);
        scrollBottom();
      }
    );
  }

  /* ==================== 四季详情浮层 ==================== */
  var SEASON_DATA = {
    spring: {
      tag: "春", title: "春 · 萌芽",
      poem: "「每一株参天，都始于一粒不肯沉默的种子」",
      desc: "春天属于所有一闪而过的念头。可能是深夜卧谈时冒出的一个点子，也可能是课堂上的一句『要是……就好了』。在「第五季」里，这些碎片不会随风吹散——知颜会陪你把它梳理清楚：它解决什么问题、需要什么资源、由谁来做，最终长成一张结构化的「项目种子卡」，在校园记忆库中正式生根。",
      feats: [
        "创意评估入库：想法先梳理成种子卡预览，你确认后才正式建档",
        "灵感暂存箱：还不够成熟的念头先存着，时机到了随时转化为项目",
        "个人档案：技能、兴趣、专业沉淀成你的数字画像"
      ],
      quote: "我有个想法：把校园天台的落日、湖边的芦苇荡做成手绘地图图文册，帮我评估一下能不能立成一个项目？"
    },
    summer: {
      tag: "夏", title: "夏 · 生长",
      poem: "「蝉声与汗水，把想法浇灌成现实」",
      desc: "夏天是动手的季节。种子卡破土之后，需要人手、需要推进、需要一次次的进展记录。「第五季」会在校园里为你寻找互补的伙伴——会画画的、会写代码的、会跑场地的；每一次推进、每一次卡壳、每一次小小的里程碑，都会被如实记录，成为项目年轮的一部分。",
      feats: [
        "伙伴匹配：按技能与兴趣标签，找到与你互补的同路人",
        "项目推进：阶段流转全程留痕（春·萌芽 → 夏·生长 → 秋·沉淀），每个节点可回溯",
        "成员协作：申请—审批制入组，同步待办、共享进展"
      ],
      quote: "我在推进手绘地图项目，帮我找几位会摄影和排版的同学一起组队。"
    },
    autumn: {
      tag: "秋", title: "秋 · 沉淀",
      poem: "「落叶归根处，是最肥沃的经验」",
      desc: "秋天不慌不忙。一个项目走到阶段性节点，比『做了什么』更重要的是『留下了什么』。知颜会帮项目做阶段总结，并提炼出一份完整的「交接包」：做成了什么、攒下哪些经验、踩过哪些坑、还有哪些未竟事项、哪些资源可以直接复用——让下一双手不必从零开始。",
      feats: [
        "阶段总结：通读项目全部动态后，提炼复盘要点",
        "交接包生成：成果 / 经验 / 踩坑 / 遗留问题 / 可复用资源，五合一沉淀",
        "待办归集：项目相关的散落事项统一收口"
      ],
      quote: "这个学期手绘地图先推进到这里，帮我做个阶段总结，并生成交接包。"
    },
    winter: {
      tag: "冬", title: "冬 · 蛰伏",
      poem: "「雪落无声，种子在等待下一双手」",
      desc: "冬天不是终点，是另一种等待。毕业季、换届季，总有些热爱不得不按下暂停键。「第五季」会让项目体面地休眠：档案全量归档、交接包封存、休眠原因写清楚——项目不会消失，只是安静地躺在校园记忆库里，等待某个春天被重新叫醒。",
      feats: [
        "项目休眠：毕业 / 换届时全量归档，保留完整上下文",
        "休眠原因记录：为什么停、停在哪一季，一目了然",
        "记忆库沉淀：休眠项目进入校园公共记忆，可被检索"
      ],
      quote: "我要毕业了，这个项目先休眠吧，把交接包封存好，等有缘人接棒。"
    },
    fifth: {
      tag: "五", title: "第五季 · 续种",
      poem: "「在春夏秋冬之外，还有一季叫重新开始」",
      desc: "这是「第五季」名字的由来。当一颗休眠的种子遇到下一届合适的人，四季的循环就有了新的起点：知颜会把休眠项目与新生们的技能、兴趣做双向匹配，推送完整的交接包；你确认接棒的那一刻，就是项目的第五季——前人的成果是你的起点，你的推进是它的重生。",
      feats: [
        "双向匹配：休眠项目 × 新同学的技能兴趣，AI 推荐接棒人选",
        "一键唤醒：确认接棒即成为新负责人，完整继承交接包",
        "传承闭环：你的第五季，也是别人某一年落下的春天"
      ],
      quote: "看看校园里有哪些休眠的项目可以接棒？我想找和我技能匹配的。"
    }
  };

  var modal = document.getElementById("season-modal");
  var modalCard = document.getElementById("season-modal-card");

  function openSeasonModal(key) {
    var d = SEASON_DATA[key];
    if (!d || !modal || !modalCard) { return; }
    document.getElementById("modal-tag").textContent = d.tag;
    document.getElementById("modal-title").textContent = d.title;
    document.getElementById("modal-poem").textContent = d.poem;
    document.getElementById("modal-desc").textContent = d.desc;
    document.getElementById("modal-quote").textContent = d.quote;
    var feats = document.getElementById("modal-feats");
    feats.innerHTML = "";
    for (var i = 0; i < d.feats.length; i++) {
      var li = document.createElement("li");
      li.textContent = d.feats[i];
      feats.appendChild(li);
    }
    modalCard.className = "season-modal-card m-" + key;
    modal.hidden = false;
    modalCard.setAttribute("data-season-key", key);
    document.body.style.overflow = "hidden";
  }

  function closeSeasonModal() {
    if (!modal) { return; }
    modal.hidden = true;
    document.body.style.overflow = "";
  }

  // 点击季节节点（含中央第五季）
  document.addEventListener("click", function (e) {
    var node = e.target.closest("[data-season]");
    if (!node) { return; }
    openSeasonModal(node.getAttribute("data-season"));
  });
  // 键盘可达：Enter / 空格
  document.addEventListener("keydown", function (e) {
    var node = e.target.closest && e.target.closest("[data-season]");
    if (node && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      openSeasonModal(node.getAttribute("data-season"));
    }
    if (e.key === "Escape") { closeSeasonModal(); }
  });
  // 关闭浮层
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-close-modal]")) { closeSeasonModal(); }
  });

  /* ==================== 档案墙折叠 ==================== */
  var archiveGrid = document.querySelector(".archive-grid");
  var archiveWrap = document.querySelector(".archive-toggle-wrap");
  var archiveBtn = document.getElementById("archive-toggle");
  var archiveText = archiveBtn ? archiveBtn.querySelector(".at-text") : null;
  var archiveHint = document.getElementById("archive-hint");
  var archiveHidden = document.querySelectorAll(".archive-card.is-collapsed");
  var archiveAll = document.querySelectorAll(".archive-card");
  if (archiveGrid && archiveBtn && archiveHidden.length) {
    archiveWrap.classList.add("can-collapse");
    archiveBtn.addEventListener("click", function () {
      var expanded = archiveGrid.classList.toggle("is-expanded");
      archiveBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
      if (archiveText) {
        archiveText.textContent = expanded
          ? "收起部分档案"
          : "展开其余 " + archiveHidden.length + " 个传承故事";
      }
      if (archiveHint) {
        archiveHint.textContent = expanded
          ? "已展开全部 " + archiveAll.length + " 份种子档案"
          : "已展示 " + (archiveAll.length - archiveHidden.length) + " / " + archiveAll.length + " · 另有 " + archiveHidden.length + " 粒种子在土壤下沉睡";
      }
    });
  }

  /* ==================== 事件绑定 ==================== */
  // 视图切换（介绍页 ↔ 对话页）
  document.addEventListener("click", function (e) {
    var el = e.target.closest("[data-action]");
    if (!el) { return; }
    var act = el.getAttribute("data-action");
    if (act === "enter-chat") {
      e.preventDefault();
      requireAuth("与知颜对话需要先登录——你的档案与跨次对话记忆都随账号保存").then(function (ok) {
        if (ok) { showView("chat"); }
      });
    }
    else if (act === "back-intro") { showView("intro"); e.preventDefault(); }
    else if (act === "try-season") {
      var key = modalCard ? modalCard.getAttribute("data-season-key") : null;
      var d = key ? SEASON_DATA[key] : null;
      closeSeasonModal();
      showView("chat");
      if (d) { send(d.quote); }
      e.preventDefault();
    }
  });

  // 快捷指令 chips
  document.addEventListener("click", function (e) {
    var chip = e.target.closest(".chip");
    if (!chip || sendBtn.disabled) { return; }
    send(chip.getAttribute("data-msg") || chip.textContent);
  });

  // 副标题点击：展开/收起「知颜」名字寓意
  var heroSub = document.getElementById("hero-sub");
  var heroMeaning = document.getElementById("hero-meaning");
  if (heroSub && heroMeaning) {
    heroSub.addEventListener("click", function () {
      heroMeaning.hidden = !heroMeaning.hidden;
    });
  }

  // hero 季节带点击：跳转对话并发送该季示例话术
  document.addEventListener("click", function (e) {
    var hs = e.target.closest(".hs-chip");
    if (!hs) { return; }
    var seasonMsg = {
      "spring": "我想在春天萌芽一个新项目想法，帮我整理成项目种子卡吧！",
      "summer": "进入夏天了，帮我的项目找找互补的搭档，推进生长！",
      "autumn": "项目要阶段性结束了，帮我做秋日沉淀，整理交接包吧。",
      "winter": "我可能没时间继续项目了，想把它休眠托管进记忆库。",
      "fifth": "我想接棒唤醒一个休眠中的项目，成为第五季的续种人！"
    };
    var cls = hs.className || "";
    for (var k in seasonMsg) {
      if (cls.indexOf(k) >= 0) { showView("chat"); send(seasonMsg[k]); return; }
    }
  });

  // 发送按钮
  if (sendBtn) {
    sendBtn.addEventListener("click", function () { send(inputEl.value); });
  }

  // 输入框自适应高度 + Enter 发送
  if (inputEl) {
    inputEl.addEventListener("input", function () {
      inputEl.style.height = "auto";
      inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
    });
    inputEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send(inputEl.value);
      }
    });
  }

  // 新会话
  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      resetSession();
      redrawHistory();
      scrollBottom();
    });
  }

  /* ==================== 移动端导航（汉堡菜单） ==================== */
  var navEl = document.querySelector(".nav");
  var navToggle = document.getElementById("nav-toggle");
  var navLinks = document.getElementById("nav-links");

  function setNavOpen(open) {
    if (!navEl || !navToggle) { return; }
    navEl.classList.toggle("is-open", open);
    navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    navToggle.setAttribute("aria-label", open ? "关闭导航菜单" : "打开导航菜单");
  }

  if (navEl && navToggle) {
    navToggle.addEventListener("click", function (e) {
      e.stopPropagation();  // 阻止冒泡到"点击面板外收起"的处理器
      setNavOpen(!navEl.classList.contains("is-open"));
    });
    // 点面板内任意链接或按钮后自动收起
    if (navLinks) {
      navLinks.addEventListener("click", function (e) {
        if (e.target.closest("a, button")) { setNavOpen(false); }
      });
    }
    // 点击面板外收起
    document.addEventListener("click", function (e) {
      if (navEl.classList.contains("is-open") && !e.target.closest(".nav")) { setNavOpen(false); }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { setNavOpen(false); }
    });
    // 视口放大回桌面端时复位，避免残留展开态
    var navMq = window.matchMedia("(min-width: 721px)");
    var onNavMq = function (m) { if (m.matches) { setNavOpen(false); } };
    if (navMq.addEventListener) { navMq.addEventListener("change", onNavMq); }
    else if (navMq.addListener) { navMq.addListener(onNavMq); }
  }

  /* ==================== 通用详情弹窗（v6.1） ==================== */
  var detailModal = document.getElementById("detail-modal");
  var detailBody = document.getElementById("detail-body");
  function openDetail(html) {
    if (!detailModal || !detailBody) { return; }
    detailBody.innerHTML = html;
    detailModal.hidden = false;
    document.documentElement.style.overflow = "hidden";
  }
  function closeDetail() {
    if (!detailModal) { return; }
    detailModal.hidden = true;
    document.documentElement.style.overflow = "";
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-close-detail]")) { closeDetail(); }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { closeDetail(); }
  });

  /* ==================== 双板块功能详情（v6.1） ==================== */
  var FEATURE_DETAILS = {
    profile: {
      icon: "📇", title: "档案建档", sub: "你的校园数字画像，一切匹配的起点",
      body: "<p>告诉知颜你的<b>昵称、年级专业、擅长技能与兴趣方向</b>，她会在对话中为你建立专属档案。档案是全系统的数据基石——六维项目匹配、前辈推荐、组队建议都基于它计算；换设备、隔学期都不会丢失，随时补充更新。</p><p>建档时若你<b>主动愿意</b>被后来人联系，可自愿留下邮箱或联系方式：同方向的新同学找前辈时，你的档案就会被推荐出来（不留则完全隐私）。</p>",
      try: "试试说：「我叫林晚，大一计算机，会写 Python 也喜欢摄影，帮我建一份档案」"
    },
    todo: {
      icon: "🗒️", title: "待办管理", sub: "自然语言记事，像朋友一样使唤",
      body: "<p>直接对知颜说「记个待办：周五 18 点前交社团招新海报」，她会解析时间、事项并关联你的项目。支持完成勾选、改期、按项目筛选；到期与项目节点会通过智能提醒主动找你，不用自己记着去查。</p>",
      try: "试试说：「记个待办，下周三之前把交接包的踩坑记录补完，关联南雍机位图鉴」"
    },
    inspiration: {
      icon: "💡", title: "灵感库", sub: "碎片想法不浪费，随时长成项目",
      body: "<p>洗澡时冒出的点子、课上突然的想法，随手丢给知颜先存进灵感库。她会为每条灵感打上标签、关联可能的项目；当某条灵感被反复提及、或与你的能力画像契合时，会提醒你——「这个想法可以立项了」。一条指令即可把灵感转化为正式的种子卡。</p>",
      try: "试试说：「存个灵感：把仙林校区流浪猫聚集点做成手绘地图」，之后说「把这条灵感转成项目」"
    },
    mentor: {
      icon: "🤝", title: "前辈连接", sub: "已建档的学长学姐，可被后来人找到",
      body: "<p>你在系统里建过档、做过项目，就自动成为「可被发现的前辈」。新同学想找同方向的人请教时，知颜按<b>技能与兴趣标签的重合度</b>推荐匹配的前辈；留过联系方式的直接展示（本人自愿公开），没留的也可以通过站内昵称先建立连接——让经验在人与人之间流动，而不只留在文档里。</p>",
      try: "试试说：「我想找做过校园地图类项目的前辈聊聊」"
    },
    seedlib: {
      icon: "🗂️", title: "项目种子库", sub: "每一个未竟，都被认真收录",
      body: "<p>你的创意会被梳理成结构化的「项目种子卡」：标题、简介、领域标签、所需能力、预期成果——知颜先呈现完整预览，<b>经你确认才正式入库</b>。已毕业学长学姐托付的项目、整理自公开报道的南大真实传承项目（研究生支教团、小百合 BBS、《蒋公的面子》……）也沉淀在这里，构成校园公共记忆库。</p>",
      try: "试试说：「我手上有个做到一半的校园播客项目，帮我立成种子卡」"
    },
    handover: {
      icon: "📦", title: "交接包生成", sub: "不止是文档，是能被接住的一整套经验",
      body: "<p>AI 通读项目全部动态，提炼五件套：<b>已有成果、执行经验、踩过的坑、遗留问题、可复用资源</b>。交接包不一定是完整代码——项目方向、已解决的问题、经验教训同样有价值：目的是让同方向的人接得住、给后来者灵感、替毕业的人完成遗憾。首页「交接包实探」可逐份点开原文验证。</p>",
      try: "试试说：「我要毕业了，把项目沉淀成交接包，资源有效期到明年 8 月」"
    },
    match: {
      icon: "🔗", title: "六维可解释匹配", sub: "推荐不是黑箱，每一分都说得清",
      body: "<p>技能互补 40 · 兴趣与议题 25 · 年级阶梯 10 · 传承准备度 10 · 社交邻近 8 · 时间投入 7。你的档案与项目画像逐维比对，<b>未知信息不臆测补分</b>，临近毕业自动降档预警，还会明确给出「待补能力」——不只告诉你匹配几分，更告诉你为什么、还缺什么。</p>",
      try: "试试说：「我是大一新生，帮我看看哪些休眠项目适合我接棒？理由说清楚」"
    },
    awaken: {
      icon: "✨", title: "唤醒接棒", sub: "第五季：让未竟重新发生",
      body: "<p>休眠项目在新一届学生手中重新落地。接棒须走<b>三步确认</b>：① 接棒者查看交接包与准备度评估、确认意愿 → ② 原负责人核验授权范围、资源有效期与原团队权益 → ③ 双方确认后正式唤醒。负责人变更、传承故事上墙、成就点亮，全程留痕——每一次唤醒都是一场被认真庆祝的接力。</p>",
      try: "试试说：「我想接棒『南雍机位图鉴』，带我先看看交接包」"
    }
  };
  document.addEventListener("click", function (e) {
    var li = e.target.closest("[data-feature]");
    if (!li) { return; }
    var f = FEATURE_DETAILS[li.getAttribute("data-feature")];
    if (!f) { return; }
    openDetail(
      '<div class="fd-head"><span class="fd-icon">' + f.icon + '</span><h3>' + f.title + '</h3><p class="fd-sub">' + f.sub + '</p></div>' +
      '<div class="fd-body">' + f.body + '</div>' +
      '<div class="fd-try">' + f.try + '</div>'
    );
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") { return; }
    var li = e.target.closest && e.target.closest("[data-feature]");
    if (!li) { return; }
    e.preventDefault();
    li.click();
  });

  /* ==================== 技能图谱大全 · 点开看项目（v6.2：项目可点开详情） ==================== */
  var STAGE_LABELS = { spring: "春·萌芽", summer: "夏·生长", autumn: "秋·沉淀", winter: "冬·蛰伏", fifth: "第五季·重生" };
  var _detailStack = []; // 支持详情弹窗内返回上级

  function openProjectDetail(projectId) {
    fetch("/api/projects/" + projectId).then(function (r) { return r.json(); }).then(function (d) {
      if (d && d.error) { openDetail('<div class="fd-body"><p>' + escapeHtml(d.error) + '</p></div>'); return; }
      var p = d.project || {};
      var h = d.handover;
      var members = d.members || [];
      var stageName = STAGE_LABELS[p.stage] || p.stage || "—";
      var skills = (p.required_skills || []).map(escapeHtml).join(" / ") || "—";
      var domains = (p.domain_tags || []).map(escapeHtml).join(" / ") || "—";

      function sec(title, arr) {
        if (!arr || !arr.length) { return ""; }
        return '<div class="pd-sec"><h5>' + title + '</h5><ul>' + arr.map(function (x) {
          return '<li>' + escapeHtml(String(x)) + '</li>';
        }).join("") + '</ul></div>';
      }

      // v10.0：未公开授权的交接包 → 提示需主人授权
      var lockedHtml = (!h && d.handover_locked) ? (
        '<p class="pd-nohandover pd-locked">📦 该项目的交接包尚未获得主人公开授权——可在对话中对知颜说「获取 FS-' + String(p.id).padStart(3, "0") + ' 的交接包」试试，或直接联系发起人 ' + escapeHtml(p.founder_nickname || "—") + ' 授权</p>'
      ) : "";
      var handoverHtml = h ? (
        '<div class="pd-handover">' +
          '<h4>📦 交接包（原团队沉淀）</h4>' +
          sec("已有成果", h.achievements) + sec("执行经验", h.experience) + sec("踩过的坑", h.pitfalls) +
          sec("遗留问题", h.remaining_issues) + sec("可复用资源", h.reusable_resources) +
          '<div class="pd-gov">' +
            '<h5>⚖️ 权益治理（尊重原团队劳动成果）</h5>' +
            '<ul>' +
              '<li><b>成果授权：</b>' + escapeHtml(h.authorization_scope || "见交接包原文") + '</li>' +
              '<li><b>资源有效期：</b>' + escapeHtml(String(h.resource_valid_until || "长期有效")) + '</li>' +
              '<li><b>原团队权益：</b>' + escapeHtml(h.founder_rights || "保留署名与贡献记录") + '</li>' +
            '</ul>' +
          '</div>' +
        '</div>'
      ) : (lockedHtml || '<p class="pd-nohandover">该项目暂无交接包——若你接棒，将与知颜一起沉淀第一份。</p>');

      var membersHtml = members.length ? (
        '<div class="pd-sec"><h5>👥 团队与接棒记录（原团队信息完整保留）</h5><ul>' +
        members.map(function (m) {
          return '<li><b>' + escapeHtml(m.nickname) + '</b> · ' + escapeHtml(m.role) +
            (m.joined_note ? '<span class="pd-note">（' + escapeHtml(m.joined_note.slice(0, 40)) + '）</span>' : '') + '</li>';
        }).join("") + '</ul></div>'
      ) : "";

      var sourceHtml = p.source_name ? (
        '<div class="pd-source">' +
          '<b>📎 公开报道</b>' +
          (p.source_url
            ? '<a class="md-link" href="' + escapeHtml(p.source_url) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(p.source_name) + '</a>'
            : '<span>' + escapeHtml(p.source_name) + '</span>') +
          '<span class="pd-source-note">（未使用本站的项目凭公开报道整理，版权与事实以原发布方为准）</span>' +
        '</div>'
      ) : "";

      openDetail(
        '<div class="fd-head"><span class="fd-icon">🌱</span><h3>' + (p.source_name ? "" : "#") + escapeHtml(p.id ? (p.source_name ? "" : p.id + " ") : "") + escapeHtml(p.title || "") + '</h3>' +
        '<p class="fd-sub">' + stageName + ' · 公开种子卡 FS-' + String(p.id).padStart(3, "0") + ' · 发起人 ' + escapeHtml(p.founder_nickname || "—") + (p.school ? ' · ' + escapeHtml(p.school) : '') + '</p></div>' +
        '<div class="fd-body">' +
          '<p>' + escapeHtml(p.summary || "") + '</p>' +
          '<div class="pd-facts">' +
            '<span><b>领域</b>' + domains + '</span>' +
            '<span><b>所需能力</b>' + skills + '</span>' +
            (p.hibernate_reason ? '<span><b>休眠原因</b>' + escapeHtml(p.hibernate_reason) + '</span>' : '') +
          '</div>' +
          '<div class="pd-actions-row">' +
            '<button class="pd-action-btn" data-msg-founder="' + escapeHtml(p.founder_nickname || "") + '">✉ 给发起人留言</button>' +
            '<button class="pd-action-btn pd-team-btn" data-create-team="' + p.id + '" data-team-title="' + escapeHtml(p.title || "") + '">🤝 发起组队</button>' +
            '<button class="pd-action-btn" data-adopt="' + p.id + '">🌱 引入我的种子库</button>' +
          '</div>' +
          sourceHtml + handoverHtml + membersHtml +
        '</div>' +
        '<div class="fd-try">接棒须知：接棒后以新团队名义补充档案，原团队的发起人署名、交接包与贡献记录全部保留。试试说：「我想接棒 #' + p.id + '，下一步该做什么？」</div>'
      );
    }).catch(function () {
      openDetail('<div class="fd-body"><p>项目详情加载失败，请稍后再试。</p></div>');
    });
  }

  document.addEventListener("click", function (e) {
    var row = e.target.closest("[data-skill]");
    if (!row) { return; }
    var skill = row.getAttribute("data-skill");
    var it = null;
    for (var i = 0; i < skillsCache.length; i++) {
      if (skillsCache[i].skill === skill) { it = skillsCache[i]; break; }
    }
    if (!it) { return; }
    var projs = it.projects || [];
    var projHtml = projs.length
      ? '<ul class="sp-list">' + projs.map(function (p) {
          return '<li class="sp-proj" data-proj-id="' + p.id + '"><span class="sp-stage">' + escapeHtml(p.stage || "—") + '</span><b>#' + p.id + ' ' + escapeHtml(p.title) + '</b><span class="sp-arrow">详情 →</span></li>';
        }).join("") + '</ul>'
      : '<p class="sp-empty">暂无项目需要这项技能——如果你拥有它，正适合发起一个新项目。</p>';
    openDetail(
      '<div class="fd-head"><span class="fd-icon">🛠️</span><h3>' + escapeHtml(skill) + '</h3>' +
      '<p class="fd-sub">需求 ' + it.demand + ' · 供给 ' + it.supply + ' · ' + (it.gap > 0 ? "稀缺能力（值得招募）" : it.gap < 0 ? "富余能力（适合发起项目）" : "供需均衡") + '</p></div>' +
      '<div class="fd-body"><p>以下是<b>需要「' + escapeHtml(skill) + '」的项目</b>（进行中 · 休眠 · 已完成传承均在列），点击任意项目查看详情：</p>' + projHtml + '</div>' +
      '<div class="fd-try">试试说：「有哪些需要' + escapeHtml(skill) + '的休眠项目适合我接棒？」</div>'
    );
  });

  /* ==================== 昵称确认弹窗（v6.1：投票/建档前置） ==================== */
  var nickModal = document.getElementById("nick-modal");
  var nickInput = document.getElementById("nick-input");
  var nickOkBtn = document.getElementById("nick-ok");
  var nickTitle = document.getElementById("nick-title");
  var nickDesc = document.getElementById("nick-desc");
  var nickResolve = null;
  function askNickname(action) {
    return new Promise(function (resolve) {
      if (!nickModal) { resolve(null); return; }
      nickResolve = resolve;
      if (action === "vote") {
        nickTitle.textContent = "投票前，请先输入你的昵称";
        nickDesc.textContent = "票数按昵称分开统计、一人一票；尚未建档的同学，知颜会在对话中帮你完成建档。";
      } else {
        nickTitle.textContent = "操作前，请先输入你的昵称";
        nickDesc.textContent = "你的昵称将用于身份识别与数据留痕（与知颜对话中使用的名字保持一致）。";
      }
      try {
        nickInput.value = localStorage.getItem("fs_nick") || "";
      } catch (err) {}
      nickModal.hidden = false;
      setTimeout(function () { nickInput.focus(); }, 30);
    });
  }
  function closeNick(result) {
    if (!nickModal) { return; }
    nickModal.hidden = true;
    if (nickResolve) { nickResolve(result); nickResolve = null; }
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-close-nick]")) { closeNick(null); }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && nickModal && !nickModal.hidden) { closeNick(null); }
    if (e.key === "Enter" && nickModal && !nickModal.hidden && document.activeElement === nickInput) {
      var v = (nickInput.value || "").trim();
      if (v) { closeNick(v); }
    }
  });
  if (nickOkBtn) {
    nickOkBtn.addEventListener("click", function () {
      var v = (nickInput.value || "").trim();
      if (!v) { nickInput.focus(); return; }
      closeNick(v);
    });
  }

  /* ==================== v8.0 种子库 ==================== */
  function loadSeeds() {
    var mineGrid = document.getElementById("seeds-mine-grid");
    var mineHint = document.getElementById("seeds-mine-hint");
    var pubGrid = document.getElementById("seeds-public-grid");
    if (!mineGrid && !pubGrid) { return; }
    // 公开种子库（v9.0：折叠展开，首屏 6 张）
    if (pubGrid) {
      fetch("/api/seeds/public").then(function (r) { return r.json(); }).then(function (d) {
        var items = (d && d.seeds) || [];
        var wrap = document.getElementById("seeds-public-wrap");
        if (!items.length) { pubGrid.innerHTML = '<div class="votes-empty">公开种子库还在生长中</div>'; return; }
        var FOLD_N = 6;
        window.__FS_PUB_SEEDS = items;
        function renderPub(startIdx, endIdx) {
          return items.slice(startIdx, endIdx).map(function (s, i) {
            var tags = (s.domain_tags || []).slice(0, 2).map(function (t) { return "<span>" + escapeHtml(t) + "</span>"; }).join("");
            // v10.0：交接包授权标记——已公开可获取 / 尚需主人授权
            var hBadge = s.kind === "personal"
              ? '<span class="ic-badge ic-handover">📦 交接包可获取</span>'
              : (s.has_handover ? (s.handover_public ? '<span class="ic-badge ic-handover">📦 交接包可获取</span>' : '<span class="ic-badge ic-lock">📦 交接包需授权</span>') : "");
            var kindBadge = s.kind === "personal" ? '<span class="ic-badge ic-school">个人项目库</span>' : (s.school ? '<span class="ic-badge ic-school">' + escapeHtml(s.school) + '</span>' : "");
            return '<article class="seed-pub-card' + (s.kind === "personal" ? " seed-pj-card" : "") + '">' +
              '<div class="seed-top"><span class="seed-code">' + escapeHtml(s.fs_code) + '</span>' + kindBadge + hBadge + '</div>' +
              '<h3>' + escapeHtml(s.title) + '</h3>' +
              '<p>' + escapeHtml((s.summary || "").slice(0, 72)) + '</p>' +
              '<div class="seed-tags">' + tags + (s.kind === "fs" ? '<span>❄ ' + s.votes + ' 票</span>' : "") + '</div>' +
              '<div class="seed-foot"><span>发起人 · ' + escapeHtml(s.owner_nickname || "—") + '</span>' +
              '<button class="seed-btn" data-seed-view="' + s.id + '" data-seed-kind="' + (s.kind || "fs") + '">查看种子卡</button></div>' +
            '</article>';
          }).join("");
        }
        pubGrid.innerHTML = renderPub(0, FOLD_N);
        var toggle = document.getElementById("seeds-public-toggle");
        if (toggle && items.length > FOLD_N) {
          toggle.hidden = false;
          toggle.textContent = "展开全部 " + items.length + " 张公开种子卡（还有 " + (items.length - FOLD_N) + " 张）";
          toggle.dataset.folded = "1";
        } else if (toggle) {
          toggle.hidden = true;
        }
      }).catch(function () { pubGrid.innerHTML = '<div class="votes-empty">公开种子库加载失败</div>'; });
    }
    // 我的种子卡（v9.0：含引入的公开种子卡）
    if (mineGrid) {
      if (!auth) {
        mineGrid.innerHTML = "";
        if (mineHint) { mineHint.hidden = false; }
        var emptyIntro = document.getElementById("seeds-intro-grid");
        if (emptyIntro) { emptyIntro.innerHTML = ""; }
        return;
      }
      fetch("/api/seeds/mine", { headers: authHeaders() }).then(function (r) { return r.json(); }).then(function (d) {
        var items = (d && d.seeds) || [];
        var intros = (d && (d.introduced || d.imported)) || [];
        if (mineHint) { mineHint.hidden = true; }
        if (!items.length) {
          mineGrid.innerHTML = '<div class="votes-empty">你的种子库还空着——在对话中把任何零碎灵感告诉知颜，她会自动存成种子卡</div>';
        } else {
          mineGrid.innerHTML = items.map(function (s) {
            var tags = (s.tags || []).map(function (t) { return "<span>" + escapeHtml(t) + "</span>"; }).join("");
            return '<article class="seed-mine-card seed-clickable" data-seed-mine="' + s.id + '" title="点开查看种子卡">' +
              '<div class="seed-top"><span class="seed-code">' + escapeHtml(s.seed_code) + '</span>' +
              (s.status === "converted" ? '<span class="ic-badge ic-handover">已长成项目</span>' : "") + '</div>' +
              '<h3>' + escapeHtml(s.title || "无题灵感") + '</h3>' +
              '<p>' + escapeHtml((s.content || "").slice(0, 90)) + '</p>' +
              (tags ? '<div class="seed-tags">' + tags + '</div>' : "") +
              '<div class="seed-foot"><span class="seed-date">' + new Date(s.created_at).toLocaleDateString() + '</span>' +
              '<span class="seed-priv">🔒 仅你可见</span></div>' +
            '</article>';
          }).join("");
        }
        // v9.0 我引入的公开种子卡
        var introGrid = document.getElementById("seeds-intro-grid");
        if (introGrid) {
          if (!intros.length) {
            introGrid.innerHTML = '<div class="votes-empty">还没有引入公开种子卡——在候选池/公开种子库看到想接手的项目，点「引入这个项目」就会出现在这里</div>';
          } else {
            introGrid.innerHTML = intros.map(function (s) {
              var tags = (s.domain_tags || []).slice(0, 3).map(function (t) { return "<span>" + escapeHtml(t) + "</span>"; }).join("");
              return '<article class="seed-pub-card seed-intro-card">' +
                '<div class="seed-top"><span class="seed-code">' + escapeHtml(s.fs_code || "") + '</span>' +
                (s.has_handover ? '<span class="ic-badge ic-handover">有交接包</span>' : "") + '</div>' +
                '<h3>' + escapeHtml(s.title) + '</h3>' +
                '<p>' + escapeHtml((s.summary || "").slice(0, 80)) + '</p>' +
                (tags ? '<div class="seed-tags">' + tags + '</div>' : "") +
                '<div class="seed-foot"><span>❄ ' + (s.votes || 0) + ' 票 · ' + escapeHtml(s.role || "接棒人") + '</span>' +
                  '<button class="seed-btn" data-seed-view="' + s.project_id + '">查看种子卡</button>' +
                  '<button class="seed-btn seed-btn-danger" data-seed-unimport="' + s.project_id + '" title="从我的种子库移除">移除</button></div>' +
              '</article>';
            }).join("");
          }
        }
      }).catch(function () {
        mineGrid.innerHTML = '<div class="votes-empty">种子库加载失败，稍后自动重试</div>';
      });
    }
  }

  document.addEventListener("click", function (e) {
    var tab = e.target.closest("[data-seeds-tab]");
    if (tab) {
      document.querySelectorAll("[data-seeds-tab]").forEach(function (t) { t.classList.toggle("active", t === tab); });
      var which = tab.getAttribute("data-seeds-tab");
      var mineP = document.getElementById("seeds-mine-panel");
      var pubP = document.getElementById("seeds-public-panel");
      var pjP = document.getElementById("seeds-projects-panel");
      if (mineP) { mineP.hidden = which !== "mine"; }
      if (pubP) { pubP.hidden = which !== "public"; }
      if (pjP) { pjP.hidden = which !== "projects"; }
      if (which === "projects") { loadMyProjects(); }
      return;
    }
    var sv = e.target.closest("[data-seed-view]");
    if (sv) {
      if (sv.getAttribute("data-seed-kind") === "personal") {
        openPersonalHandover(parseInt(sv.getAttribute("data-seed-view"), 10));
      } else {
        openProjectDetail(parseInt(sv.getAttribute("data-seed-view"), 10));
      }
      return;
    }
    // v10.0 需求④：移除已引入的公开种子卡
    var un = e.target.closest("[data-seed-unimport]");
    if (un) {
      var upid = parseInt(un.getAttribute("data-seed-unimport"), 10);
      if (window.confirm("确定从我的种子库移除这张公开种子卡吗？（不影响项目本身与其他成员）")) {
        fetch("/api/projects/" + upid + "/unimport", { method: "DELETE", headers: authHeaders() })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.success) { loadSeeds(); }
            else { window.alert(d.error || "移除失败"); }
          });
      }
      return;
    }
    // v10.0 需求⑤：点开个人种子卡查看
    var sm = e.target.closest("[data-seed-mine]");
    if (sm) { openSeedCardDetail(parseInt(sm.getAttribute("data-seed-mine"), 10)); return; }
  });

  /* ==================== v10.0 个人种子卡详情 ==================== */
  var __mineSeedsCache = [];
  function openSeedCardDetail(seedId) {
    // 从 /api/seeds/mine 缓存中取（避免重复请求）
    fetch("/api/seeds/mine", { headers: authHeaders() }).then(function (r) { return r.json(); }).then(function (d) {
      __mineSeedsCache = (d && d.seeds) || [];
      var seed = null;
      for (var i = 0; i < __mineSeedsCache.length; i++) {
        if (parseInt(__mineSeedsCache[i].id, 10) === seedId) { seed = __mineSeedsCache[i]; break; }
      }
      if (!seed) { return; }
      var tags = (seed.tags || []).map(function (t) { return '<span class="seed-tag-pill">' + escapeHtml(t) + '</span>'; }).join("");
      openDetail(
        '<div class="fd-head"><span class="fd-icon">🌱</span><h3>' + escapeHtml(seed.title || "无题灵感") + '</h3>' +
        '<p class="fd-sub">个人种子卡 ' + escapeHtml(seed.seed_code || "") + ' · 🔒 仅你可见 · ' + new Date(seed.created_at).toLocaleString() + '</p></div>' +
        '<div class="fd-body">' +
          '<div class="pd-facts">' +
            '<span><b>状态</b>' + (seed.status === "converted" ? "已长成项目" : "灵感收藏") + '</span>' +
            (seed.project_id ? '<span><b>关联项目</b>FS-' + String(seed.project_id).padStart(3, "0") + '</span>' : "") +
          '</div>' +
          (tags ? '<div class="seed-tags seed-tags-lg">' + tags + '</div>' : "") +
          '<div class="pd-sec"><h5>📝 灵感原文</h5><p class="pd-seed-content">' + escapeHtml(seed.content || "") + '</p></div>' +
          '<div class="pd-actions-row">' +
            '<button class="pd-action-btn pd-team-btn" data-msg-ai-seed="' + escapeHtml(seed.seed_code || "") + '">💬 和知颜聊聊这个灵感</button>' +
          '</div>' +
        '</div>' +
        '<div class="fd-try">种子卡是你零碎灵感的收藏盒。想让它走得更远？对知颜说：「把 ' + escapeHtml(seed.seed_code || "这个灵感") + ' 提炼成项目」，她会帮你整理成完整的种子卡档案。</div>'
      );
    });
  }

  /* ==================== v10.0 个人项目库 ==================== */
  var PJ_STATUS = { ongoing: "🌱 进行中", unfinished: "🌫 未完成", taken_over: "🤲 接棒中", done: "✅ 已完成" };
  function loadMyProjects() {
    var grid = document.getElementById("pj-grid");
    if (!grid) { return; }
    if (!auth) {
      grid.innerHTML = '<div class="votes-empty">登录后即可拥有你的个人项目库——与种子卡不同，这里存放完整的项目档案（仅你可见）</div>';
      return;
    }
    grid.innerHTML = '<div class="votes-empty">正在加载你的项目库…</div>';
    fetch("/api/my-projects", { headers: authHeaders() }).then(function (r) { return r.json(); }).then(function (d) {
      var projects = (d && d.projects) || [];
      if (!projects.length) {
        grid.innerHTML = '<div class="votes-empty">你的项目库还空着——点上方「新建项目档案」，或对知颜说「帮我在项目库里记录一个新项目」</div>';
        return;
      }
      grid.innerHTML = projects.map(function (p) {
        var tags = (p.tags || []).slice(0, 3).map(function (t) { return "<span>" + escapeHtml(t) + "</span>"; }).join("");
        return '<article class="pj-card">' +
          '<div class="seed-top"><span class="seed-code">' + escapeHtml(p.fs_code || ("PJ-" + String(p.id).padStart(3, "0"))) + '</span>' +
          (p.has_handover ? '<span class="ic-badge ic-handover">📦 有交接包</span>' : "") +
          (p.handover_public ? '<span class="ic-badge ic-open">🌍 已公开</span>' : "") + '</div>' +
          '<h3>' + escapeHtml(p.title) + '</h3>' +
          '<p>' + escapeHtml((p.summary || "暂无简介").slice(0, 80)) + '</p>' +
          '<div class="seed-tags">' + tags + '<span>' + (PJ_STATUS[p.status] || p.status) + '</span></div>' +
          '<div class="seed-foot"><span class="seed-date">' + new Date(p.updated_at || p.created_at).toLocaleDateString() + '</span></div>' +
          '<div class="pj-actions">' +
            '<button class="seed-btn" data-pj-open="' + p.id + '">查看</button>' +
            '<button class="seed-btn" data-pj-handover="' + p.id + '">' + (p.has_handover ? "重制交接包" : "📦 生成交接包") + '</button>' +
            '<button class="seed-btn' + (p.handover_public ? " seed-btn-warn" : " seed-btn-go") + '" data-pj-public="' + p.id + '" data-val="' + (p.handover_public ? "0" : "1") + '"' + (!p.has_handover && !p.handover_public ? ' title="先生成交接包才能公开"' : '') + '>' + (p.handover_public ? "取消公开" : "🌍 公开交接包") + '</button>' +
            '<button class="seed-btn seed-btn-danger" data-pj-del="' + p.id + '">删除</button>' +
          '</div>' +
        '</article>';
      }).join("");
    }).catch(function () {
      grid.innerHTML = '<div class="votes-empty">项目库加载失败，稍后自动重试</div>';
    });
  }

  function openPersonalProject(pid) {
    fetch("/api/my-projects", { headers: authHeaders() }).then(function (r) { return r.json(); }).then(function (d) {
      var p = null;
      ((d && d.projects) || []).forEach(function (x) { if (parseInt(x.id, 10) === pid) { p = x; } });
      if (!p) { return; }
      var pkg = p.handover_package || {};
      function sec(title, arr) {
        if (!arr || !arr.length) { return ""; }
        return '<div class="pd-sec"><h5>' + title + '</h5><ul>' + arr.map(function (x) { return '<li>' + escapeHtml(String(x)) + '</li>'; }).join("") + '</ul></div>';
      }
      var govHtml = pkg.authorization_scope ? (
        '<div class="pd-gov"><h5>⚖️ 权益治理</h5><ul>' +
          '<li><b>成果授权：</b>' + escapeHtml(pkg.authorization_scope || "") + '</li>' +
          '<li><b>资源有效期：</b>' + escapeHtml(String(pkg.resource_valid_until || "长期有效")) + '</li>' +
          '<li><b>原团队权益：</b>' + escapeHtml(pkg.founder_rights || "保留署名") + '</li>' +
        '</ul></div>'
      ) : "";
      var pkgHtml = p.has_handover ? (
        '<div class="pd-handover"><h4>📦 交接包' + (p.handover_public ? '（已公开，他人可获取）' : '（未公开）') + '</h4>' +
        sec("已有成果", pkg.achievements) + sec("执行经验", pkg.experience) + sec("踩过的坑", pkg.pitfalls) +
        sec("遗留问题", pkg.remaining_issues) + sec("可复用资源", pkg.reusable_resources) + govHtml + '</div>'
      ) : '<p class="pd-nohandover">还没有交接包——点「📦 生成交接包」，知颜会基于项目档案帮你提炼</p>';
      openDetail(
        '<div class="fd-head"><span class="fd-icon">📁</span><h3>' + escapeHtml(p.title) + '</h3>' +
        '<p class="fd-sub">个人项目库 PJ-' + String(p.id).padStart(3, "0") + ' · 🔒 仅你可见 · ' + (PJ_STATUS[p.status] || p.status) + '</p></div>' +
        '<div class="fd-body">' +
          '<p>' + escapeHtml(p.summary || "") + '</p>' +
          (p.description ? '<div class="pd-sec"><h5>📋 项目详情</h5><p class="pd-seed-content">' + escapeHtml(p.description).replace(/\n/g, "<br>") + '</p></div>' : "") +
          (p.source_project_id ? '<div class="pd-facts"><span><b>来源种子卡</b>FS-' + String(p.source_project_id).padStart(3, "0") + '</span></div>' : "") +
          pkgHtml +
          '<div class="pd-actions-row">' +
            '<button class="pd-action-btn pd-team-btn" data-msg-ai-pj="' + p.id + '">💬 让知颜接手这个项目</button>' +
          '</div>' +
        '</div>' +
        '<div class="fd-try">想公开交接包？点卡片上的「🌍 公开交接包」，或对知颜说「把 PJ-' + String(p.id).padStart(3, "0") + ' 的交接包公开」——公开后其他人可以在公开种子库或对话中获取。</div>'
      );
    });
  }

  function openPersonalHandover(pid) {
    // 公开种子库中的 PJ 卡：获取公开交接包
    fetch("/api/handover/personal/" + pid).then(function (r) { return r.json(); }).then(function (d) {
      if (!d || d.error) {
        openDetail('<div class="fd-body"><p>' + escapeHtml((d && d.error) || "获取失败") + '</p></div>');
        return;
      }
      var p = d.project || {};
      var h = d.handover || {};
      function sec(title, arr) {
        if (!arr || !arr.length) { return ""; }
        return '<div class="pd-sec"><h5>' + title + '</h5><ul>' + arr.map(function (x) { return '<li>' + escapeHtml(String(x)) + '</li>'; }).join("") + '</ul></div>';
      }
      openDetail(
        '<div class="fd-head"><span class="fd-icon">📦</span><h3>' + escapeHtml(p.title) + '</h3>' +
        '<p class="fd-sub">个人项目库 ' + escapeHtml(p.fs_code || "") + ' · 发起人 ' + escapeHtml(p.owner_nickname || "—") + ' · 🌍 交接包已公开</p></div>' +
        '<div class="fd-body">' +
          '<p>' + escapeHtml(p.summary || "") + '</p>' +
          '<div class="pd-handover"><h4>📦 交接包（原主人沉淀）</h4>' +
          sec("已有成果", h.achievements) + sec("执行经验", h.experience) + sec("踩过的坑", h.pitfalls) +
          sec("遗留问题", h.remaining_issues) + sec("可复用资源", h.reusable_resources) +
          (h.authorization_scope ? '<div class="pd-gov"><h5>⚖️ 权益治理（尊重原主人劳动成果）</h5><ul>' +
            '<li><b>成果授权：</b>' + escapeHtml(h.authorization_scope) + '</li>' +
            '<li><b>资源有效期：</b>' + escapeHtml(String(h.resource_valid_until || "长期有效")) + '</li>' +
            '<li><b>原团队权益：</b>' + escapeHtml(h.founder_rights || "保留署名") + '</li>' +
          '</ul></div>' : "") +
          '</div>' +
          '<div class="pd-actions-row"><button class="pd-action-btn pd-team-btn" data-msg-founder="' + escapeHtml(p.owner_nickname || "") + '">✉ 给主人留言</button></div>' +
        '</div>' +
        '<div class="fd-try">想接棒这个项目？对知颜说：「我想接手 ' + escapeHtml(p.fs_code || "") + '，帮我评估下一步」。</div>'
      );
    });
  }

  // 项目库卡片操作（查看 / 生成交接包引导 / 公开开关 / 删除 / 新建）
  document.addEventListener("click", function (e) {
    var pjOpen = e.target.closest("[data-pj-open]");
    if (pjOpen) { openPersonalProject(parseInt(pjOpen.getAttribute("data-pj-open"), 10)); return; }
    var pjHv = e.target.closest("[data-pj-handover]");
    if (pjHv) {
      var hid = parseInt(pjHv.getAttribute("data-pj-handover"), 10);
      enterChatWith("帮我把项目库里的 PJ-" + String(hid).padStart(3, "0") + " 生成交接包：请先读一下它的完整档案，再基于真实内容提炼五段式清单和治理声明。");
      return;
    }
    var pjPub = e.target.closest("[data-pj-public]");
    if (pjPub) {
      var pubId = parseInt(pjPub.getAttribute("data-pj-public"), 10);
      var want = pjPub.getAttribute("data-val") === "1";
      fetch("/api/my-projects/" + pubId, {
        method: "PATCH",
        headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
        body: JSON.stringify({ handover_public: want })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d.success) { loadMyProjects(); }
        else { window.alert(d.error || "操作失败"); }
      });
      return;
    }
    var pjDel = e.target.closest("[data-pj-del]");
    if (pjDel) {
      var delId = parseInt(pjDel.getAttribute("data-pj-del"), 10);
      if (window.confirm("确定删除这个项目档案吗？交接包也会一并删除，不可恢复。")) {
        fetch("/api/my-projects/" + delId, { method: "DELETE", headers: authHeaders() })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.success) { loadMyProjects(); }
            else { window.alert(d.error || "删除失败"); }
          });
      }
      return;
    }
    var pjNew = e.target.closest("#pj-new-btn");
    if (pjNew) { openPjNewForm(); return; }
    // 灵感种子卡 → 对话
    var aiSeed = e.target.closest("[data-msg-ai-seed]");
    if (aiSeed) {
      enterChatWith("我想聊聊种子卡 " + aiSeed.getAttribute("data-msg-ai-seed") + " 的想法，帮我分析一下可行性和下一步。");
      return;
    }
    var aiPj = e.target.closest("[data-msg-ai-pj]");
    if (aiPj) {
      enterChatWith("请帮我看看项目库里的 PJ-" + String(parseInt(aiPj.getAttribute("data-msg-ai-pj"), 10)).padStart(3, "0") + "：读一下它的完整档案，给我一些推进建议。");
      return;
    }
  });

  function openPjNewForm() {
    requireAuth("项目库需要先登录").then(function (ok) {
      if (!ok) { return; }
      openDetail(
        '<div class="fd-head"><span class="fd-icon">📁</span><h3>新建项目档案</h3>' +
        '<p class="fd-sub">仅你可见 · 可随时让知颜生成/更新交接包</p></div>' +
        '<div class="fd-body">' +
          '<div class="pj-form">' +
            '<label>项目名称<b>*</b><input type="text" id="pj-f-title" maxlength="80" placeholder="如：宿舍楼共享雨伞计划"/></label>' +
            '<label>一句话简介<input type="text" id="pj-f-summary" maxlength="200" placeholder="用一句话说明它是什么"/></label>' +
            '<label>项目状态<select id="pj-f-status">' +
              '<option value="ongoing">🌱 进行中</option>' +
              '<option value="unfinished">🌫 未完成</option>' +
              '<option value="taken_over">🤲 接棒中</option>' +
              '<option value="done">✅ 已完成</option>' +
            '</select></label>' +
            '<label>标签（逗号分隔）<input type="text" id="pj-f-tags" maxlength="60" placeholder="如：公益,生活服务"/></label>' +
            '<label>项目详情（目标 / 已有进展 / 成果 / 当前卡点）<textarea id="pj-f-desc" rows="6" maxlength="4000" placeholder="写得越完整，知颜之后帮你生成交接包时就越准"></textarea></label>' +
            '<div class="pj-form-actions">' +
              '<button class="nick-cancel" data-close-detail type="button">取消</button>' +
              '<button class="nick-ok" id="pj-f-submit" type="button">存入项目库</button>' +
            '</div>' +
          '</div>' +
        '</div>'
      );
      var submit = document.getElementById("pj-f-submit");
      if (submit) {
        submit.addEventListener("click", function () {
          var title = (document.getElementById("pj-f-title").value || "").trim();
          if (!title) { window.alert("请填写项目名称"); return; }
          var tags = (document.getElementById("pj-f-tags").value || "").split(/[,，、\s]+/).filter(Boolean).slice(0, 8);
          fetch("/api/my-projects", {
            method: "POST",
            headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
            body: JSON.stringify({
              title: title,
              summary: (document.getElementById("pj-f-summary").value || "").trim(),
              description: (document.getElementById("pj-f-desc").value || "").trim(),
              status: document.getElementById("pj-f-status").value,
              tags: tags
            })
          }).then(function (r) { return r.json(); }).then(function (d) {
            if (d.success) {
              closeDetail();
              var tab = document.querySelector('[data-seeds-tab="projects"]');
              if (tab) { tab.click(); } else { loadMyProjects(); }
            } else { window.alert(d.error || "保存失败"); }
          });
        });
      }
    });
  }

  /* ==================== v10.0 个人项目库 ==================== */

  /* ==================== v8.0 组队空间 ==================== */
  function loadTeams() {
    var grid = document.getElementById("teams-grid");
    var myGrid = document.getElementById("my-teams-grid");
    if (!grid && !myGrid) { return; }
    if (!auth) {
      // v9.0：招募区对所有用户可见（含未登录访客）；「我的团队」仅登录后展示
      if (myGrid) { myGrid.innerHTML = '<div class="votes-empty">登录后查看你的团队</div>'; }
    }
    fetch("/api/teams", { headers: authHeaders() }).then(function (r) { return r.json(); }).then(function (d) {
      var teams = (d && d.teams) || [];
      var mine = (d && d.my_teams) || [];
      if (myGrid && !auth) {
        myGrid.innerHTML = '<div class="votes-empty">登录后查看你的团队</div>';
      } else if (myGrid) {
        myGrid.innerHTML = mine.length ? mine.map(function (t) {
          return '<article class="team-card">' +
            '<div class="team-top"><span class="team-badge">' + (t.role === "队长" ? "👑 队长" : "👤 成员") + '</span>' +
            '<span class="team-status ' + (t.status === "approved" ? "ok" : "wait") + '">' +
            (t.status === "approved" ? (t.team_status === "active" ? "协作中" : "招募中") : "待审批") + '</span></div>' +
            '<h3>' + escapeHtml(t.name) + '</h3>' +
            '<p class="team-meta">' + t.member_count + ' 人</p>' +
            '<button class="seed-btn" data-team-open="' + t.id + '">进入团队空间</button>' +
          '</article>';
        }).join("") : '<div class="votes-empty">你还没有团队——在公开种子库找心仪的项目，或自己在组队空间发一队</div>';
      }
      if (grid) {
        grid.innerHTML = teams.length ? teams.map(function (t) {
          var proj = t.project ? '<p class="team-proj">🌱 ' + escapeHtml(t.project.title) + '</p>' : "";
          var poster = t.poster_url ? '<img class="team-poster team-poster-click" src="' + escapeHtml(t.poster_url) + '" alt="招募海报" loading="lazy" data-poster-zoom="' + escapeHtml(t.poster_url) + '" title="点击放大查看">' : "";
          var mineInfo = t.my_status === "pending" ? '<button class="vote-btn is-voted" disabled>待队长审批</button>' :
            (t.my_status === "approved" ? '<button class="vote-btn is-voted" disabled>✓ 已是成员</button>' :
            '<button class="vote-btn" data-team-apply="' + t.id + '">申请加入</button>');
          return '<article class="team-card">' +
            '<div class="team-top"><span class="team-badge">📣 招募中</span><span class="team-meta">' + t.member_count + ' 人</span></div>' +
            poster +
            '<h3>' + escapeHtml(t.name) + '</h3>' +
            proj +
            '<p>' + escapeHtml((t.description || "").slice(0, 70)) + '</p>' +
            '<p class="team-meta">队长 · ' + escapeHtml(t.leader_nickname || "—") + '</p>' +
            '<div class="vote-actions">' +
            '<button class="vote-view" data-team-open="' + t.id + '">详情</button>' + mineInfo + '</div>' +
          '</article>';
        }).join("") : '<div class="votes-empty">现在没有招募中的团队——做第一个发队的人：点上方「发布招募」，或在公开种子卡上「发起组队」</div>';
      }
    }).catch(function () {
      if (grid) { grid.innerHTML = '<div class="votes-empty">组队空间加载失败，稍后自动重试</div>'; }
    });
  }

  var teamModal = document.getElementById("team-modal");
  var currentTeam = null;

  function openTeamModal(tid) {
    if (!teamModal) { return; }
    requireAuth("查看团队空间需要先登录").then(function (ok) {
      if (!ok) { return; }
      fetch("/api/teams/" + tid, { headers: authHeaders() }).then(function (r) { return r.json(); }).then(function (d) {
        if (!d || d.error) { alert((d && d.error) || "团队不存在"); return; }
        currentTeam = d;
        var head = document.getElementById("team-head");
        var membersEl = document.getElementById("team-members");
        var appsEl = document.getElementById("team-apps");
        var chatWrap = document.getElementById("team-chat-wrap");
        var isMember = d.is_leader || d.my_status === "approved";
        head.innerHTML = '<div class="auth-ornament"><i></i><b>🤝</b><i></i></div>' +
          '<h3>' + escapeHtml(d.name) + '</h3>' +
          '<p>' + escapeHtml((d.description || "").slice(0, 100)) + ' · 队长 ' + escapeHtml(d.leader_nickname || "—") +
          (d.project ? ' · 🌱 ' + escapeHtml(d.project.title) : "") + '</p>';
        // v10.0 需求①：项目现状（招募详情 = 团队成员 + 项目现状）
        var projBox = document.getElementById("team-project-box");
        if (projBox) {
          if (d.project) {
            var pj = d.project;
            var pjStage = STAGE_LABELS[pj.stage] || pj.stage || "—";
            var pjSkills = (pj.required_skills || []).slice(0, 6).join(" / ") || "—";
            var pjDomains = (pj.domain_tags || []).slice(0, 4).join(" / ") || "—";
            projBox.hidden = false;
            projBox.innerHTML = '<h4>🌱 项目现状</h4>' +
              '<div class="tp-row"><b>' + escapeHtml(pj.title) + '</b><span>FS-' + String(pj.id).padStart(3, "0") + ' · ' + escapeHtml(pjStage) + '</span></div>' +
              '<p class="tp-summary">' + escapeHtml((pj.summary || "").slice(0, 160)) + '</p>' +
              '<div class="tp-facts"><span><b>领域</b>' + escapeHtml(pjDomains) + '</span><span><b>所需能力</b>' + escapeHtml(pjSkills) + '</span></div>' +
              '<div class="tp-actions"><button class="seed-btn" data-seed-view="' + pj.id + '">查看完整种子卡</button></div>';
          } else { projBox.hidden = true; projBox.innerHTML = ""; }
        }
        // 成员（v10.0 需求③：成员间可留言）
        var approved = (d.members || []).filter(function (m) { return m.status === "approved"; });
        membersEl.innerHTML = "<h4>成员（" + (approved.length + 1) + "）</h4>" +
          '<div class="tm-list">' +
          '<div class="tm-item"><b>👑 ' + escapeHtml(d.leader_nickname || "队长") + '</b><span>队长</span>' +
            (d.is_leader ? "" : '<button class="tm-msg-btn" data-member-msg="' + escapeHtml(d.leader_nickname || "") + '">✉ 留言</button>') + '</div>' +
          approved.map(function (m) {
            return '<div class="tm-item"><b>' + escapeHtml(m.nickname || "—") + '</b><span>' +
              escapeHtml((m.grade || "") + " " + (m.major || "")) + '</span>' +
              (m.nickname && auth && m.nickname !== auth.n ? '<button class="tm-msg-btn" data-member-msg="' + escapeHtml(m.nickname) + '">✉ 留言</button>' : "") + '</div>';
          }).join("") + '</div>';
        // 待审批（仅队长）
        if (d.is_leader) {
          var pending = (d.members || []).filter(function (m) { return m.status === "pending"; });
          appsEl.innerHTML = pending.length ? "<h4>待审批申请</h4>" + pending.map(function (m) {
            return '<div class="tm-app"><div><b>' + escapeHtml(m.nickname || "—") + '</b> ' +
              escapeHtml((m.grade || "") + " " + (m.major || "")) +
              (m.skills && m.skills.length ? ' · 会 ' + escapeHtml(m.skills.slice(0, 3).join("/")) : "") + '</div>' +
              (m.persona_public ? '<p class="tm-persona">' + escapeHtml(m.persona_public) + '</p>' : "") +
              (m.note ? '<p class="tm-note">“' + escapeHtml(m.note.slice(0, 80)) + '”</p>' : "") +
              '<div class="tm-actions"><button class="tm-ok" data-approve="' + m.user_id + '">通过</button>' +
              '<button class="tm-no" data-reject="' + m.user_id + '">婉拒</button></div></div>';
          }).join("") : "";
        } else { appsEl.innerHTML = ""; }
        // 协作空间（成员可见）——v10.0 需求③：加载全队共享对话历史（互相可见）
        if (chatWrap) {
          chatWrap.hidden = !isMember;
          if (isMember) {
            var msgs = document.getElementById("team-chat-messages");
            if (msgs) {
              msgs.innerHTML = '<div class="tc-hint">这是团队的共同对话空间——知颜与全队共用一份记忆，所有人聊过的内容彼此可见</div>';
              fetch("/api/teams/" + tid + "/chat", { headers: authHeaders() })
                .then(function (r) { return r.json(); })
                .then(function (hd) {
                  var list = (hd && hd.messages) || [];
                  if (!list.length) { return; }
                  msgs.innerHTML = "";
                  list.forEach(function (m) {
                    var isMe = auth && m.nickname === auth.n;
                    var who = m.role === "assistant" ? "知颜" : (m.nickname + (isMe ? "（我）" : ""));
                    msgs.insertAdjacentHTML("beforeend",
                      '<div class="tc-msg ' + (m.role === "assistant" ? "ai" : (isMe ? "me" : "other")) + '">' +
                      '<b>' + escapeHtml(who) + '</b><p>' + escapeHtml(m.content) + '</p></div>');
                  });
                  msgs.scrollTop = msgs.scrollHeight;
                });
            }
          }
        }
        // v9.0 招募海报（展示 + 队长可换）
        var posterBox = document.getElementById("team-poster-box");
        if (posterBox) {
          posterBox.hidden = !d.poster_url && !d.is_leader;
          posterBox.innerHTML = d.poster_url
            ? '<h4>招募海报（点击放大）</h4><img class="team-poster team-poster-big team-poster-click" src="' + escapeHtml(d.poster_url) + '" alt="招募海报" data-poster-zoom="' + escapeHtml(d.poster_url) + '">' +
              (d.is_leader ? '<div class="tm-actions"><label class="tm-ok" style="text-align:center;cursor:pointer">更换海报<input type="file" id="team-poster-input" accept="image/*" hidden></label></div>' : "")
            : '<h4>招募海报</h4><div class="votes-empty" style="margin:0">还没有海报——上传一张你的招募海报吧（支持图片）</div>' +
              (d.is_leader ? '<div class="tm-actions"><label class="tm-ok" style="text-align:center;cursor:pointer">上传海报<input type="file" id="team-poster-input" accept="image/*" hidden></label></div>' : "");
          var posterInput = document.getElementById("team-poster-input");
          if (posterInput) {
            posterInput.addEventListener("change", function () {
              var f = posterInput.files && posterInput.files[0];
              if (!f) { return; }
              var fr = new FileReader();
              fr.onload = function () {
                fetch("/api/teams/" + tid + "/poster", {
                  method: "PUT",
                  headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
                  body: JSON.stringify({ poster: String(fr.result || "") })
                }).then(function (r) { return r.json(); }).then(function (res) {
                  if (res.success) { openTeamModal(tid); loadTeams(); }
                  else { alert(res.error || "海报上传失败"); }
                }).catch(function () { alert("海报上传失败，请重试"); });
              };
              fr.readAsDataURL(f);
            });
          }
        }
        teamModal.hidden = false;
      });
    });
  }

  document.addEventListener("click", function (e) {
    var open = e.target.closest("[data-team-open]");
    if (open) { openTeamModal(parseInt(open.getAttribute("data-team-open"), 10)); return; }
    var apply = e.target.closest("[data-team-apply]");
    if (apply) {
      e.preventDefault();
      var tid = parseInt(apply.getAttribute("data-team-apply"), 10);
      requireAuth("申请入队需要先登录").then(function (ok) {
        if (!ok) { return; }
        var note = (prompt("向队长简单介绍你自己与加入意愿（队长会在信箱看到）：") || "").trim();
        fetch("/api/teams/" + tid + "/apply", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
          body: JSON.stringify({ note: note })
        }).then(function (r) { return r.json(); }).then(function (d) {
          alert((d && (d.message || d.error)) || "已提交");
          loadTeams();
        });
      });
      return;
    }
    var ap = e.target.closest("[data-approve]");
    if (ap && currentTeam) {
      fetch("/api/teams/" + currentTeam.id + "/approve", {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
        body: JSON.stringify({ user_id: parseInt(ap.getAttribute("data-approve"), 10) })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d.success) { openTeamModal(currentTeam.id); loadTeams(); }
        else { alert(d.error || "操作失败"); }
      });
      return;
    }
    var rj = e.target.closest("[data-reject]");
    if (rj && currentTeam) {
      fetch("/api/teams/" + currentTeam.id + "/reject", {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
        body: JSON.stringify({ user_id: parseInt(rj.getAttribute("data-reject"), 10) })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d.success) { openTeamModal(currentTeam.id); loadTeams(); }
        else { alert(d.error || "操作失败"); }
      });
      return;
    }
    if (e.target.closest("[data-close-team]")) { teamModal && (teamModal.hidden = true); }
    // v10.0 海报灯箱
    var pz = e.target.closest("[data-poster-zoom]");
    if (pz) {
      var lb = document.getElementById("poster-lightbox");
      var limg = document.getElementById("poster-lightbox-img");
      if (lb && limg) { limg.src = pz.getAttribute("data-poster-zoom"); lb.hidden = false; }
      return;
    }
    if (e.target.closest("[data-close-lightbox]")) {
      var lbx = document.getElementById("poster-lightbox");
      if (lbx) { lbx.hidden = true; }
      return;
    }
    // 候选池种子卡快捷查看
    var vs = e.target.closest("[data-view-seed]");
    if (vs) { openProjectDetail(parseInt(vs.getAttribute("data-view-seed"), 10)); }
    // ===== v9.0 新增交互 =====
    // 档案故事点开全文
    var so = e.target.closest("[data-story-open]");
    if (so) {
      var sid = so.getAttribute("data-story-open");
      fetch("/api/stories/" + sid).then(function (r) { return r.json(); }).then(function (d) {
        if (!d || d.error) { alert("故事加载失败"); return; }
        var mask = document.getElementById("story-modal");
        if (!mask) { return; }
        var setTitle = function (id, v) { var el = document.getElementById(id); if (el) { el.textContent = v || ""; } };
        setTitle("story-d-title", d.title);
        setTitle("story-d-meta", (d.era || "") + " · " + (d.school || "") + " · 整理自公开报道");
        var tagsBox = document.getElementById("story-d-tags");
        if (tagsBox) {
          tagsBox.innerHTML = (d.tags || []).map(function (t) {
            return '<span class="story-hl">✦ ' + escapeHtml(t) + '</span>';
          }).join("");
        }
        var bodyBox = document.getElementById("story-d-body");
        if (bodyBox) {
          bodyBox.innerHTML = (d.story_full || "").split("\n").map(function (para) {
            return para.trim() ? '<p>' + escapeHtml(para) + '</p>' : "";
          }).join("");
        }
        var footBox = document.getElementById("story-d-foot");
        if (footBox) {
          footBox.innerHTML =
            (d.source_name ? '<p class="st-source">素材来源：' + escapeHtml(d.source_name) +
              (d.source_url ? ' · <a href="' + escapeHtml(d.source_url) + '" target="_blank" rel="noopener">查看原文报道 ↗</a>' : "") + '</p>' : "") +
            '<p class="st-note">※ 本故事基于真实校园项目经历整理，部分情节与人物称呼已做艺术加工</p>';
        }
        mask.hidden = false;
      });
      return;
    }
    if (e.target.closest("[data-close-story]")) {
      var sm = document.getElementById("story-modal"); if (sm) { sm.hidden = true; }
    }
    // 候选池类型展开（v9.0：每类型仅展示榜首，其余在此弹窗查看）
    var to = e.target.closest("[data-group-open]");
    if (to) {
      var tname = to.getAttribute("data-group-open");
      var pool = (dormantGroups && dormantGroups[tname]) || [];
      if (!pool.length) { return; }
      var tmask = document.getElementById("group-modal");
      var tgrid = document.getElementById("group-modal-grid");
      if (!tmask || !tgrid) { return; }
      var gt = document.getElementById("group-d-title");
      if (gt) { gt.textContent = tname + " · 休眠项目"; }
      var gs = document.getElementById("group-d-sub");
      if (gs) { gs.textContent = "共 " + pool.length + " 个" + tname + "方向的休眠种子，按票数排序——票数越高越优先被唤醒"; }
      tgrid.innerHTML = pool.map(function (p) { return renderVoteCard(p); }).join("");
      tmask.hidden = false;
      return;
    }
    if (e.target.closest("[data-close-group]")) {
      var tm2 = document.getElementById("group-modal"); if (tm2) { tm2.hidden = true; }
    }
    // 公开种子库折叠
    var pt = e.target.closest("#seeds-public-toggle");
    if (pt) {
      var pubGrid2 = document.getElementById("seeds-public-grid");
      var items2 = window.__FS_PUB_SEEDS || [];
      if (pt.dataset.folded === "1") {
        pubGrid2.innerHTML = items2.map(function (s, i) {
          var tags = (s.domain_tags || []).slice(0, 2).map(function (t) { return "<span>" + escapeHtml(t) + "</span>"; }).join("");
          return '<article class="seed-pub-card">' +
            '<div class="seed-top"><span class="seed-code">' + escapeHtml(s.fs_code) + '</span>' +
            (s.school ? '<span class="ic-badge ic-school">' + escapeHtml(s.school) + '</span>' : "") +
            (s.has_handover ? '<span class="ic-badge ic-handover">有交接包</span>' : "") + '</div>' +
            '<h3>' + escapeHtml(s.title) + '</h3>' +
            '<p>' + escapeHtml((s.summary || "").slice(0, 72)) + '</p>' +
            '<div class="seed-tags">' + tags + '<span>❄ ' + s.votes + ' 票</span></div>' +
            '<div class="seed-foot"><span>发起人 · ' + escapeHtml(s.owner_nickname || "—") + '</span>' +
            '<button class="seed-btn" data-seed-view="' + s.id + '">查看种子卡</button></div>' +
          '</article>';
        }).join("");
        pt.dataset.folded = "0";
        pt.textContent = "收起，只看前 6 张";
      } else {
        loadSeeds();
      }
      return;
    }
    // 风云榜完整版
    var lb = e.target.closest("[data-lb-open]");
    if (lb) { openLeaderboardModal(); return; }
    if (e.target.closest("[data-close-lb]")) { closeLeaderboardModal(); }
    // 风云榜里看画像
    var lbp = e.target.closest("[data-lb-profile]");
    if (lbp) {
      closeLeaderboardModal();
      openPublicProfile(lbp.getAttribute("data-lb-profile"));
      return;
    }
    // 功能手册（导航栏 data-action="open-handbook"）
    var man = e.target.closest('[data-action="open-handbook"]');
    if (man) {
      var mm = document.getElementById("handbook-modal");
      if (mm) {
        var hb = document.getElementById("handbook-body");
        if (hb && !hb.dataset.rendered) { hb.innerHTML = HANDBOOK_HTML; hb.dataset.rendered = "1"; }
        mm.hidden = false;
      }
      return;
    }
    if (e.target.closest("[data-close-handbook]")) {
      var mm2 = document.getElementById("handbook-modal"); if (mm2) { mm2.hidden = true; }
    }
    // 发布招募（teams-toolbar data-action="open-recruit"）
    var pr = e.target.closest('[data-action="open-recruit"]');
    if (pr) {
      requireAuth("发布招募需要先登录").then(function (ok) {
        if (!ok) { return; }
        var rm = document.getElementById("recruit-modal"); if (rm) { rm.hidden = false; }
      });
      return;
    }
    if (e.target.closest("[data-close-recruit]")) {
      var rm2 = document.getElementById("recruit-modal"); if (rm2) { rm2.hidden = true; }
    }
  });

  // v9.0 发布招募（队名+说明+可选海报，海报先传后建队）
  (function () {
    var submit = document.getElementById("recruit-submit");
    if (!submit) { return; }
    var posterFileInput = document.getElementById("recruit-poster-file");
    var posterBtn = document.getElementById("recruit-poster-btn");
    var previewBox = document.getElementById("recruit-poster-preview");
    var previewImg = document.getElementById("recruit-poster-img");
    var posterDel = document.getElementById("recruit-poster-del");
    var chosenPoster = null;
    if (posterBtn && posterFileInput) {
      posterBtn.addEventListener("click", function () { posterFileInput.click(); });
    }
    if (posterFileInput) {
      posterFileInput.addEventListener("change", function () {
        chosenPoster = posterFileInput.files && posterFileInput.files[0];
        if (chosenPoster && previewBox && previewImg) {
          previewImg.src = URL.createObjectURL(chosenPoster);
          previewBox.hidden = false;
        }
      });
    }
    if (posterDel) {
      posterDel.addEventListener("click", function () {
        chosenPoster = null;
        if (posterFileInput) { posterFileInput.value = ""; }
        if (previewBox) { previewBox.hidden = true; }
      });
    }
    submit.addEventListener("click", function () {
      if (!auth) { return; }
      var name = ((document.getElementById("recruit-name") || {}).value || "").trim();
      var desc = ((document.getElementById("recruit-desc") || {}).value || "").trim();
      if (!name) { alert("给队伍起个名字吧"); return; }
      function createTeam(posterDataUrl) {
        fetch("/api/teams", {
          method: "POST",
          headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
          body: JSON.stringify({ name: name, description: desc, project_id: null, poster: posterDataUrl || null })
        }).then(function (r) { return r.json(); }).then(function (d) {
          if (d.success) {
            var rm = document.getElementById("recruit-modal"); if (rm) { rm.hidden = true; }
            var rn = document.getElementById("recruit-name"); if (rn) { rn.value = ""; }
            var rd = document.getElementById("recruit-desc"); if (rd) { rd.value = ""; }
            if (posterDel) { posterDel.click(); }
            loadTeams();
            alert("招募已发布！成员申请会通过知颜留言送到你的信箱");
          } else { alert(d.error || "发布失败"); }
        }).catch(function () { alert("发布失败，请重试"); });
      }
      if (chosenPoster) {
        var fr = new FileReader();
        fr.onload = function () { createTeam(String(fr.result || "")); };
        fr.onerror = function () { createTeam(null); };
        fr.readAsDataURL(chosenPoster);
      } else { createTeam(null); }
    });
  })();

  // 团队协作空间对话（独立 SSE，thread=team-{id}）
  var tcSendBtn = document.getElementById("team-chat-send");
  var tcInput = document.getElementById("team-chat-input");
  function teamChatSend() {
    if (!tcInput || !currentTeam) { return; }
    var text = (tcInput.value || "").trim();
    if (!text) { return; }
    tcInput.value = "";
    var box = document.getElementById("team-chat-messages");
    box.insertAdjacentHTML("beforeend", '<div class="tc-msg me"><b>' + escapeHtml(auth ? auth.n : "我") + '</b><p>' + escapeHtml(text) + '</p></div>');
    box.scrollTop = box.scrollHeight;
    var aiDiv = document.createElement("div");
    aiDiv.className = "tc-msg ai";
    aiDiv.innerHTML = "<b>知颜</b><p></p>";
    box.appendChild(aiDiv);
    var p = aiDiv.querySelector("p");
    fetch("/api/chat", {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
      body: JSON.stringify({ message: text, team_id: currentTeam.id })
    }).then(function (resp) {
      var reader = resp.body.getReader();
      var dec = new TextDecoder();
      var buf = "";
      function pump() {
        return reader.read().then(function (r) {
          if (r.done) { box.scrollTop = box.scrollHeight; return; }
          buf += dec.decode(r.value, { stream: true });
          var lines = buf.split("\n");
          buf = lines.pop();
          lines.forEach(function (ln) {
            if (ln.indexOf("data: ") !== 0) { return; }
            try {
              var d = JSON.parse(ln.slice(6));
              if (d.type === "delta") { p.textContent += d.text || ""; box.scrollTop = box.scrollHeight; }
              if (d.type === "tool") { p.textContent += "⏳ " + (d.label || "") + "… "; }
            } catch (err) {}
          });
          return pump();
        });
      }
      return pump();
    });
  }
  if (tcSendBtn) { tcSendBtn.addEventListener("click", teamChatSend); }
  if (tcInput) {
    tcInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); teamChatSend(); }
    });
  }

  /* ==================== v8.0 个人画像 ==================== */
  var profileModal = document.getElementById("profile-modal");
  // v9.0 查看他人公开画像
  function openPublicProfile(nickname) {
    if (!nickname) { return; }
    fetch("/api/profile/" + encodeURIComponent(nickname)).then(function (r) { return r.json(); }).then(function (d) {
      if (!d || d.error) { alert((d && d.error) || "对方未公开画像"); return; }
      var pm = document.getElementById("profile-modal");
      var box = document.getElementById("profile-modal");
      if (!pm) { return; }
      var pe = d.persona || {};
      var setRO = function (id, v) {
        var el = document.getElementById(id);
        if (el) { el.value = v || ""; el.readOnly = true; }
      };
      setRO("pf-traits", pe.traits); setRO("pf-strengths", pe.strengths);
      setRO("pf-story", pe.story); setRO("pf-goals", pe.goals);
      var pub = document.getElementById("pf-public");
      if (pub) { pub.checked = false; pub.disabled = true; }
      var errEl = document.getElementById("pf-error");
      if (errEl) { errEl.style.color = "#9b8a70"; errEl.textContent = "正在查看「" + nickname + "」的公开画像（只读）"; }
      pm.dataset.readonly = nickname;
      pm.hidden = false;
    }).catch(function () { alert("画像加载失败"); });
  }
  function openProfileModal() {
    if (!profileModal) { return; }
    requireAuth("查看画像需要先登录").then(function (ok) {
      if (!ok) { return; }
      delete profileModal.dataset.readonly;
      var pub = document.getElementById("pf-public");
      if (pub) { pub.disabled = false; }
      ["pf-traits", "pf-strengths", "pf-story", "pf-goals"].forEach(function (id) {
        var el = document.getElementById(id); if (el) { el.readOnly = false; }
      });
      fetch("/api/profile", { headers: authHeaders() }).then(function (r) { return r.json(); }).then(function (d) {
        var pe = d.persona || {};
        var set = function (id, v) { var el = document.getElementById(id); if (el) { el.value = v || ""; } };
        set("pf-traits", pe.traits); set("pf-strengths", pe.strengths);
        set("pf-story", pe.story); set("pf-goals", pe.goals);
        var pub = document.getElementById("pf-public");
        if (pub) { pub.checked = !!d.profile_public; }
        var errEl = document.getElementById("pf-error");
        if (errEl) { errEl.textContent = ""; }
        profileModal.hidden = false;
      });
    });
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-action='open-profile']")) { e.preventDefault(); openProfileModal(); return; }
    if (e.target.closest("[data-close-profile]")) { profileModal && (profileModal.hidden = true); return; }
    var save = e.target.closest("#pf-save");
    if (save && profileModal && !profileModal.hidden) {
      if (profileModal.dataset.readonly) { return; }  // v9.0 查看他人画像时只读
      var val = function (id) { var el = document.getElementById(id); return el ? (el.value || "").trim() : ""; };
      var persona = { traits: val("pf-traits"), strengths: val("pf-strengths"), story: val("pf-story"), goals: val("pf-goals") };
      var pub = document.getElementById("pf-public");
      fetch("/api/profile", {
        method: "PUT",
        headers: Object.assign({ "Content-Type": "application/json" }, authHeaders()),
        body: JSON.stringify({ persona: persona, profile_public: pub ? pub.checked : false })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d.success) {
          var errEl = document.getElementById("pf-error");
          if (errEl) { errEl.style.color = "#3d7a4e"; errEl.textContent = "已保存" + (pub && pub.checked ? "（画像已公开）" : "（仅自己可见）"); }
        }
      });
    }
  });

  /* ==================== v8.0 文件上传 ==================== */
  var btnUpload = document.getElementById("btn-upload");
  var chatFile = document.getElementById("chat-file");
  if (btnUpload && chatFile) {
    btnUpload.addEventListener("click", function () {
      requireAuth("上传文件建档需要先登录").then(function (ok) { if (ok) { chatFile.click(); } });
    });
    chatFile.addEventListener("change", function () {
      var f = chatFile.files && chatFile.files[0];
      if (!f) { return; }
      var fd = new FormData();
      fd.append("file", f);
      var old = btnUpload.innerHTML;
      btnUpload.innerHTML = "…";
      fetch("/api/upload", { method: "POST", headers: authHeaders(), body: fd }).then(function (r) { return r.json(); }).then(function (d) {
        btnUpload.innerHTML = old;
        if (d && d.file_id) {
          showView("chat");
          send("我上传了文件「" + d.file_name + "」（file_id=" + d.file_id + "，" + d.chars + " 字），请通读后帮我整理建档：生成项目种子卡与档案。有不明晰的地方请温柔地问我确认。");
        } else {
          alert((d && d.error) || "上传失败");
        }
        chatFile.value = "";
      }).catch(function () { btnUpload.innerHTML = old; alert("上传失败，请重试"); chatFile.value = ""; });
    });
  }

  /* ==================== v8.0 新手教程 ==================== */
  var TOUR_STEPS = [
    { sel: "#nav-auth", title: "第 1 步 · 从登录开始", text: "点「进入/注册」输入昵称即可建档，系统发放六位专属传承码。凭「昵称+传承码」登录后，你的档案、种子卡、项目库与对话记忆都会一直跟着你。" },
    { sel: ".nav-cta", title: "第 2 步 · 和知颜对话（核心）", text: "她是你的传承学姐。试试这样说：「我是大二会Python的，想做点公益」→ 她做能力推理与项目匹配；「我有个宿舍雨伞角的想法」→ 存成个人种子卡；「帮我在项目库记录新项目」→ 建档 PJ-#N。第一次对话她会自我介绍并为你生成个人画像。" },
    { sel: "#votes", title: "第 3 步 · 休眠种子 · 需求投票", text: "按类型分组的休眠项目池，每组展示榜首；标题行右侧「展开 +N」小按钮可看全部候选。想复活哪个就点「我也想用」投票，票数决定唤醒优先级；点「种子卡」看完整档案。" },
    { sel: "#seeds", title: "第 4 步 · 种子库三件套", text: "三个标签页：「我的种子卡」（零碎灵感，点开可看详情）；「公开种子库」（FS-#N 项目档案 + PJ-#N 公开交接包，卡片角标显示交接包可否获取，可一键引入/移除）；「我的项目库」（完整项目档案，仅你可见）。" },
    { sel: "#seeds", title: "第 5 步 · 个人项目库（新）", text: "存放你自己的完整项目：未完成的想法、正在接棒的项目都行。点「新建项目档案」或对知颜说「在项目库记录一个新项目」；点「📦 生成交接包」让知颜基于档案提炼五段式清单；「🌍 公开交接包」后其他人就能在公开种子库或对话中获取。" },
    { sel: "#teams", title: "第 6 步 · 组队空间", text: "招募区海报点击可放大；点「详情」看项目现状与全部成员。申请通过后进入团队协作空间：全队共用一份知颜记忆，对话记录互相可见；成员旁「✉ 留言」可直接给 TA 递话。" },
    { sel: "#import", title: "第 7 步 · 项目引入", text: "搜到心仪的项目后点「引入我的种子库」，以新团队名义接棒，原团队的信息与贡献完整保留。想看前人成果？对知颜说「获取 FS-017 的交接包」。" },
    { sel: "#skills", title: "第 8 步 · 技能图谱", text: "点技能标签看校园里谁会什么、哪些能力稀缺；从技能直接跳到可参与的项目，也可以让知颜帮你牵线搭伙。" },
    { sel: "#nav-auth", title: "第 9 步 · 信箱与画像", text: "铃铛是留言信箱——同学、队友通过知颜给你递话都会到这里；旁边的画像是你的个人档案，可编辑、可决定是否公开。" },
    { sel: ".nav-plain[data-action='open-handbook']", title: "第 10 步 · 随时回来查手册", text: "这份教程只有 10 步，但「功能手册」里有全部功能的详细说明和知颜对话模拟示例（照着说就能用）。传承是一场接力——愿你接住的那颗种子，也能在你手里长成树。" }
  ];
  var tourOverlay = document.getElementById("tour-overlay");
  var tourStep = 0;
  function tourShow(i) {
    if (!tourOverlay) { return; }
    if (i < 0) { i = 0; }
    if (i >= TOUR_STEPS.length) { tourOverlay.hidden = true; return; }
    tourStep = i;
    var st = TOUR_STEPS[i];
    var target = document.querySelector(st.sel);
    var spot = document.getElementById("tour-spotlight");
    var bubble = document.getElementById("tour-bubble");
    var no = document.getElementById("tour-step-no");
    if (target) {
      target.scrollIntoView({ block: "center", behavior: "smooth" });
      var r = target.getBoundingClientRect();
      spot.style.top = (r.top - 8) + "px";
      spot.style.left = (r.left - 8) + "px";
      spot.style.width = (r.width + 16) + "px";
      spot.style.height = (r.height + 16) + "px";
      spot.hidden = false;
    } else { spot.hidden = true; }
    document.getElementById("tour-title").textContent = st.title;
    document.getElementById("tour-text").textContent = st.text;
    no.textContent = (i + 1) + " / " + TOUR_STEPS.length;
    document.getElementById("tour-prev").style.visibility = i === 0 ? "hidden" : "visible";
    document.getElementById("tour-next").textContent = i === TOUR_STEPS.length - 1 ? "完成 ✓" : "下一步";
    bubble.style.top = "";
    bubble.style.bottom = "32px";
    bubble.style.left = "50%";
    bubble.style.right = "";
    tourOverlay.hidden = false;
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-action='start-tour']")) { e.preventDefault(); tourShow(0); return; }
    if (e.target.closest("#tour-next")) { tourShow(tourStep + 1); return; }
    if (e.target.closest("#tour-prev")) { tourShow(tourStep - 1); return; }
    if (e.target.closest("#tour-skip")) { tourOverlay && (tourOverlay.hidden = true); return; }
  });
  document.addEventListener("keydown", function (e) {
    if (tourOverlay && !tourOverlay.hidden) {
      if (e.key === "Escape") { tourOverlay.hidden = true; }
      if (e.key === "ArrowRight") { tourShow(tourStep + 1); }
    }
  });

  /* ==================== 初始化 ==================== */
  loadAuth();
  if (auth) { saveAuth(auth); }  // 恢复会话时同步认证 cookie
  renderNavAuth();
  renderGrade();
  var initialView = "intro";
  try {
    var requestedView = new URLSearchParams(window.location.search).get("view");
    if (requestedView === "chat" || requestedView === "intro") { initialView = requestedView; }
    var saved = sessionStorage.getItem(STORE_KEY);
    if (!requestedView && (saved === "chat" || saved === "intro")) { initialView = saved; }
  } catch (e) {}
  showView(initialView);
  loadLegacySections();
})();
