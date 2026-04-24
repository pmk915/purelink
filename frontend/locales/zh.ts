import type { Messages } from "./en";

export const zh: Messages = {
  common: {
    loadingWorkspace: "正在加载 PureLink 工作区...",
    loading: "加载中...",
    language: "语言",
    noDescription: "暂时还没有描述。",
    noDescriptionProvided: "暂时还没有提供描述。",
    updatedAt: "更新于",
    create: "创建",
    createInvite: "创建邀请码",
    name: "名称",
    description: "描述",
    inviteCode: "邀请码",
    signOut: "退出登录",
    apiDocs: "API 文档",
    open: "打开",
    anonymous: "访客",
    openNavigation: "打开导航",
    review: "审核",
    processing: "处理",
    status: "状态",
    personal: "个人",
    team: "团队",
    admin: "管理员",
    member: "成员",
    user: "用户",
    assistant: "助手",
    uploaded: "上传于",
    teamId: (id: number) => `团队 #${id}`,
    knowledgeBaseId: (id: number) => `知识库 #${id}`,
    conversationId: (id: number) => `会话 #${id}`,
    taskId: (id: number) => `任务 #${id}`,
    expires: "过期时间",
    submittedBy: (id: number) => `提交用户 #${id}`,
    chunk: (id: string) => `片段 ${id}`,
    documentId: (id: number) => `文档 #${id}`,
    shortKnowledgeBaseId: (id: number) => `知识库 #${id}`
  },
  nav: {
    dashboard: "工作台",
    knowledgeBases: "知识库",
    teams: "团队",
    conversations: "会话",
    mvpTitle: "使用提示",
    brandSubtitle: "团队知识工作台",
    mvpDescription:
      "打开知识库、上传文档，并从上次中断的位置继续。"
  },
  topbar: {
    searchPlaceholder: "搜索功能会在下一轮更完整的前端迭代中加入",
    newKnowledgeBase: "新建知识库",
    language: "语言"
  },
  authLayout: {
    eyebrow: "PureLink",
    title: "把知识、文档与 AI 问答放到一个工作区里。",
    description:
      "PureLink 帮助团队整理文档、审核共享内容、搜索知识，并继续之前保存的问答会话。",
    listTitle: "你可以在这里：",
    bullets: [
      "创建个人和团队知识空间",
      "上传文档并管理审核流程",
      "搜索已收录内容并发起提问",
      "基于引用片段继续历史会话"
    ]
  },
  auth: {
    login: {
      title: "登录",
      description:
        "使用你的 PureLink 账户进入个人和团队知识工作区。",
      identifier: "邮箱或用户名",
      password: "密码",
      submit: "登录",
      submitting: "登录中...",
      switchPrompt: "还没有账号？",
      switchAction: "去注册",
      fallbackError: "登录失败。"
    },
    register: {
      title: "创建账号",
      description:
        "先从个人知识库开始，再逐步进入团队协作流程。",
      email: "邮箱",
      username: "用户名",
      password: "密码",
      submit: "创建账号",
      submitting: "创建中...",
      switchPrompt: "已经有账号？",
      switchAction: "去登录",
      fallbackError: "注册失败。"
    }
  },
  dashboard: {
    label: "工作台",
    welcome: (username: string) => `欢迎回来，${username}。`,
    intro:
      "从这里继续你的知识工作：进入知识库、上传文档，并回到最近的会话。",
    openKnowledgeBases: "打开知识库",
    openTeams: "打开团队",
    openConversations: "打开会话",
    quickActionsTitle: "快捷操作",
    quickActionsDescription:
      "把最常用的动作放在最前面。",
    newKnowledgeBase: "新建知识库",
    quickActionKnowledgeBases:
      "创建新的知识库，或者继续处理已有知识库。",
    quickActionTeams:
      "管理团队空间、成员和审核任务。",
    quickActionConversations:
      "回到之前的问答记录，继续追问和整理。",
    recentKnowledgeBasesTitle: "最近使用的知识库",
    recentKnowledgeBasesDescription:
      "快速回到你正在使用的空间。",
    recentKnowledgeBasesEmpty:
      "还没有知识库。先创建一个，再开始添加文档。",
    recentTeamsTitle: "最近使用的团队",
    recentTeamsDescription:
      "团队成员可以在这里共同上传、审核和使用知识。",
    recentTeamsEmpty:
      "还没有团队。你可以自己创建，或者通过邀请码加入。",
    recentConversationsTitle: "最近会话",
    recentConversationsDescription:
      "从上次保存的位置继续，不用重新开始。",
    recentConversationsEmpty:
      "还没有保存的会话。先在知识库中提问，系统就会自动生成会话记录。",
    stats: {
      personalKnowledgeBases: "个人知识库",
      teams: "团队",
      conversations: "会话"
    },
    managePersonal: "管理个人知识库",
  },
  knowledgeBases: {
    title: "个人知识库",
    description: "你的私有工作区会按所有者做严格隔离。",
    empty: "还没有个人知识库。先创建一个，再开始添加文档。",
    loading: "正在加载知识库...",
    loadError: "加载知识库失败。",
    createTitle: "新建个人知识库",
    createDescription:
      "为你的文档、问题和回答创建一个专属空间。",
    createError: "创建知识库失败。",
    openWorkspace: "进入工作区",
    notFoundTitle: "知识库不存在",
    notFoundDescription:
      "当前用户可能没有权限访问这个工作区。",
    uploadTitle: "上传文档",
    uploadDescriptionPersonal:
      "当前支持 .txt、.md、.pdf、.docx、.mp3、.wav、.m4a、.mp4、.mov、.m4v、.png、.jpg 和 .jpeg。上传后 PureLink 可以将文档准备为可搜索、可问答的内容。",
    uploadDescriptionTeam:
      "当前支持 .txt、.md、.pdf、.docx、.mp3、.wav、.m4a、.mp4、.mov、.m4v、.png、.jpg 和 .jpeg。团队文档需要先审核通过，之后才能进入知识库搜索。",
    documentsTitle: "文档",
    documentsDescription: "查看每个文档的状态，并在需要时继续处理。",
    noDocuments: "还没有文档。",
    workspaceScopePersonal: "个人知识库",
    workspaceScopeTeam: (teamId: number) => `团队知识库 · team #${teamId}`,
    activeTaskTitle: "当前任务",
    activeTaskDescription:
      "这个面板会轮询最近一次从工作区触发的任务状态。"
  },
  documents: {
    chooseFileError: "请先选择一个 .txt、.md、.pdf、.docx、.mp3、.wav、.m4a、.mp4、.mov、.m4v、.png、.jpg 或 .jpeg 文件。",
    unsupportedFileType: "当前产品界面只支持上传 .txt、.md、.pdf、.docx、.mp3、.wav、.m4a、.mp4、.mov、.m4v、.png、.jpg 和 .jpeg 文件。",
    supportedFormats: "支持格式：.txt、.md、.pdf、.docx、.mp3、.wav、.m4a、.mp4、.mov、.m4v、.png、.jpg、.jpeg",
    uploadSubmit: "上传文档",
    uploading: "上传中...",
    uploadFailed: "上传失败。",
    uploadSucceeded: (filename: string) => `${filename} 上传成功。`,
    uploadSubmittedForReview: (filename: string) =>
      `${filename} 已上传，并已提交审核。`,
    uploadProcessingStarted: (filename: string) =>
      `${filename} 已上传，PureLink 正在为搜索和问答做准备。`,
    processingSubmitted: (filename: string) =>
      `${filename} 已提交到后台处理，请稍后刷新查看最新状态。`,
    uploadReady: (filename: string) =>
      `${filename} 已可用于搜索和问答。`,
    uploadedAt: "上传于",
    reviewComment: "审核备注",
    processStart: "开始处理",
    processContinue: "继续处理",
    processRetry: "重新处理",
    processingNow: "处理中",
    processingSuccess: "已就绪",
    processingFailed: "处理失败",
    processingTimeout: "处理耗时较长，请稍后刷新查看结果。",
    statusAvailable: "可搜索",
    statusAvailableHint: "该文档已经可以用于搜索和问答。",
    statusPendingReview: "待审核",
    statusPendingReviewHint:
      "需要团队管理员先审核通过，文档才能正式进入知识库。",
    statusRejected: "需要修改",
    statusRejectedHint:
      "该文档未通过审核，请根据备注调整后重新上传。",
    statusUploaded: "已上传",
    statusUploadedHint:
      "文档已经进入知识库，接下来可以继续处理。",
    statusProcessing: "处理中",
    statusProcessingHint:
      "PureLink 正在准备该文档，使其可用于搜索和问答。",
    statusFailed: "处理失败",
    statusFailedHint:
      "准备过程中出现问题，请重新尝试。",
    statusUnsupported: "暂不支持",
    statusUnsupportedHint:
      "当前界面只支持将 .txt、.md、.pdf、.docx、.mp3、.wav、.m4a、.mp4、.mov、.m4v、.png、.jpg 和 .jpeg 文档继续处理为可搜索内容。",
    statusReadyToContinue: "待继续处理",
    statusReadyToContinueHint:
      "该文档已完成部分准备，可以继续进入最后一步。"
  },
  qa: {
    retrieveTitle: "检索上下文",
    retrieveDescription: (scopeLabel: string) =>
      `先从当前知识库中找出最相关的内容。当前范围：${scopeLabel}。`,
    retrieveQuery: "检索问题",
    retrieveTopK: "Top K",
    retrieveSubmit: "开始检索",
    retrieving: "检索中...",
    retrieveFailed: "检索失败。",
    askTitle: "向 PureLink 提问",
    askDescription:
      "围绕当前知识库发起提问，相关引用会持续显示在右侧。",
    askQuestion: "问题",
    askTopK: "Top K",
    askSubmit: "开始问答",
    asking: "回答中...",
    askFailed: "问答失败。",
    answerTitle: "回答",
    citationsTitle: "引用片段",
    citationsDescription:
      "当前回答对应的相关文档片段会显示在这里。",
    citationsEmpty: "还没有引用。先检索或直接提问。",
    citationPage: (page: number) => `第 ${page} 页`,
    citationSection: (section: string) => `章节：${section}`,
    citationHeadingPath: (path: string) => `标题：${path}`,
    citationCharRange: (start: number, end: number) => `字符 ${start}-${end}`,
    citationImageRegion: "OCR 文本区域",
    citationTimeRange: (start: string, end: string) => `${start} - ${end}`,
    citationScore: (score: number) => `分数 ${score.toFixed(3)}`,
    openConversation: (id: number) => `打开会话 #${id}`
  },
  teams: {
    pageTitle: "我的团队",
    pageDescription: "团队模块承载协作、审核和共享知识库。",
    pageLoading: "正在加载团队...",
    pageLoadError: "加载团队失败。",
    pageEmpty: "还没有团队。你可以自己创建，或者通过邀请码加入。",
    createTitle: "创建团队",
    createDescription: "先创建一个共享工作区，你会自动成为第一个管理员。",
    createError: "创建团队失败。",
    createSubmit: "创建团队",
    creating: "创建中...",
    joinTitle: "通过邀请码加入",
    joinDescription: "粘贴管理员给你的邀请码即可加入团队。",
    joinError: "加入团队失败。",
    joinSubmit: "加入团队",
    joining: "加入中...",
    openTeam: "进入团队",
    roleAdmin: "管理员",
    roleMember: "成员",
    detailLabel: "团队工作区",
    loadingTeam: "正在加载团队...",
    reviewsLink: "进入审核队列",
    membersTitle: "团队成员",
    membersDescription: "当前团队中所有处于激活状态的成员。",
    inviteTitle: "邀请队友",
    inviteDescription: "创建邀请码，供新成员加入团队。",
    expiresInDays: "过期天数",
    inviteError: "创建邀请码失败。",
    teamKnowledgeBasesTitle: "团队知识库",
    teamKnowledgeBasesDescription:
      "用于沉淀已审核通过的团队共享知识。",
    teamKnowledgeBasesEmpty: "还没有团队知识库。",
    createKbTitle: "新建团队知识库",
    createKbDescription:
      "团队知识结构由管理员负责维护。",
    permissionsTitle: "权限说明",
    permissionsBody:
      "你可以访问团队知识库并提交文档，但只有管理员可以创建邀请码、创建团队知识库，以及审核团队文档。"
  },
  reviews: {
    label: "审核队列",
    title: "待审核团队文档",
    description:
      "只有团队管理员可以通过或拒绝团队成员提交的文档。审核通过后，文档才能继续进入知识库。",
    approvalNote:
      "通过审核只会改变审核结果。文档仍需继续处理后，才会变成可搜索状态。",
    rejectReason: "拒绝原因",
    rejectSubmit: "拒绝",
    rejecting: "拒绝中...",
    rejectError: "拒绝文档失败。",
    approveSubmit: "通过",
    approving: "通过中...",
    empty: "当前没有待审核任务。"
  },
  conversations: {
    pageLabel: "会话历史",
    pageTitle: "已保存的问答会话",
    pageDescription:
      "会话由 ask 流程自动持久化，并始终关联到底层知识库。",
    loading: "正在加载会话...",
    emptyTitle: "还没有会话",
    emptyBody: "先从知识库里发起问答，系统才会开始积累会话历史。",
    openConversation: "打开会话",
    summaryLabel: "会话概览",
    messagesTitle: "消息",
    messagesDescription: "这里会展示已保存的用户消息、助手回答和引用片段。",
    notFound: "会话不存在",
    loadingSingle: "正在加载会话..."
  }
};
