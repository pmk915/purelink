export const en = {
  common: {
    loadingWorkspace: "Loading PureLink workspace...",
    loading: "Loading...",
    language: "Language",
    noDescription: "No description yet.",
    noDescriptionProvided: "No description provided yet.",
    updatedAt: "Updated",
    create: "Create",
    createInvite: "Create invite",
    name: "Name",
    description: "Description",
    inviteCode: "Invite code",
    signOut: "Sign out",
    apiDocs: "API docs",
    open: "Open",
    anonymous: "Anonymous",
    openNavigation: "Open navigation",
    review: "review",
    processing: "processing",
    status: "Status",
    personal: "Personal",
    team: "Team",
    admin: "Admin",
    member: "Member",
    user: "User",
    assistant: "Assistant",
    uploaded: "Uploaded",
    teamId: (id: number) => `Team #${id}`,
    knowledgeBaseId: (id: number) => `KB #${id}`,
    conversationId: (id: number) => `Conversation #${id}`,
    taskId: (id: number) => `Task #${id}`,
    expires: "Expires",
    submittedBy: (id: number) => `Submitted by user #${id}`,
    chunk: (id: string) => `Excerpt ${id}`,
    documentId: (id: number) => `doc #${id}`,
    shortKnowledgeBaseId: (id: number) => `kb #${id}`
  },
  nav: {
    dashboard: "Workbench",
    knowledgeBases: "Knowledge Bases",
    teams: "Teams",
    conversations: "Conversations",
    mvpTitle: "Quick tip",
    brandSubtitle: "Team knowledge workspace",
    mvpDescription:
      "Open a knowledge base, upload documents, and continue where you left off."
  },
  topbar: {
    searchPlaceholder:
      "Search is reserved for a future richer frontend pass",
    newKnowledgeBase: "New knowledge base",
    language: "Language"
  },
  authLayout: {
    eyebrow: "PureLink",
    title: "Knowledge, documents, and AI answers in one workspace.",
    description:
      "PureLink helps teams organize documents, review shared content, search knowledge, and continue saved conversations.",
    listTitle: "What you can do:",
    bullets: [
      "Create personal and team knowledge spaces",
      "Upload documents and manage review flows",
      "Search approved content and ask questions",
      "Continue saved conversations with citations"
    ]
  },
  auth: {
    login: {
      title: "Sign in",
      description:
        "Use your PureLink account to access personal and team knowledge workspaces.",
      identifier: "Email or username",
      password: "Password",
      submit: "Sign in",
      submitting: "Signing in...",
      switchPrompt: "No account yet?",
      switchAction: "Create one",
      fallbackError: "Unable to sign in."
    },
    register: {
      title: "Create account",
      description:
        "Start with your own knowledge base, then expand into team collaboration.",
      email: "Email",
      username: "Username",
      password: "Password",
      submit: "Create account",
      submitting: "Creating account...",
      switchPrompt: "Already have an account?",
      switchAction: "Sign in",
      fallbackError: "Unable to register."
    }
  },
  dashboard: {
    label: "Workbench",
    welcome: (username: string) => `Welcome back, ${username}.`,
    intro:
      "Pick up your knowledge work, upload new documents, and return to recent conversations from here.",
    openKnowledgeBases: "Open knowledge bases",
    openTeams: "Open teams",
    openConversations: "Open conversations",
    quickActionsTitle: "Quick actions",
    quickActionsDescription:
      "Start from the actions people use most often.",
    newKnowledgeBase: "New knowledge base",
    quickActionKnowledgeBases:
      "Create a new knowledge base or continue an existing one.",
    quickActionTeams:
      "Manage team spaces, members, and review work.",
    quickActionConversations:
      "Return to previous Q&A sessions and continue the discussion.",
    recentKnowledgeBasesTitle: "Recent knowledge bases",
    recentKnowledgeBasesDescription:
      "Jump back into the spaces you are actively using.",
    recentKnowledgeBasesEmpty:
      "No knowledge bases yet. Create your first one to start adding documents.",
    recentTeamsTitle: "Recent teams",
    recentTeamsDescription:
      "Shared spaces where your team uploads, reviews, and uses knowledge together.",
    recentTeamsEmpty:
      "No teams yet. Create one or join with an invite code.",
    recentConversationsTitle: "Recent conversations",
    recentConversationsDescription:
      "Resume saved Q&A sessions without starting over.",
    recentConversationsEmpty:
      "No saved conversations yet. Ask a question from a knowledge base to create one.",
    stats: {
      personalKnowledgeBases: "Personal knowledge bases",
      teams: "Teams",
      conversations: "Conversations"
    },
    managePersonal: "Manage personal knowledge bases"
  },
  knowledgeBases: {
    title: "Personal knowledge bases",
    description: "Your private workspaces are isolated by owner.",
    empty:
      "No personal knowledge bases yet. Create one to start adding documents.",
    loading: "Loading knowledge bases...",
    loadError: "Unable to load knowledge bases.",
    createTitle: "New personal knowledge base",
    createDescription:
      "Create a focused space for your documents, questions, and answers.",
    createError: "Unable to create knowledge base.",
    openWorkspace: "Open workspace",
    notFoundTitle: "Knowledge base not found",
    notFoundDescription:
      "The current user may not have access to this workspace.",
    uploadTitle: "Upload document",
    uploadDescriptionPersonal:
      "Supported formats: .txt, .md, .pdf, .docx, .mp3, .wav, .m4a, .mp4, .mov, .m4v, .png, .jpg, and .jpeg. After upload, PureLink can prepare the document for search and Q&A.",
    uploadDescriptionTeam:
      "Supported formats: .txt, .md, .pdf, .docx, .mp3, .wav, .m4a, .mp4, .mov, .m4v, .png, .jpg, and .jpeg. Team documents must be approved before they become searchable.",
    documentsTitle: "Documents",
    documentsDescription:
      "Track each document, confirm whether it is ready, and process it when needed.",
    noDocuments: "No documents yet.",
    workspaceScopePersonal: "personal knowledge base",
    workspaceScopeTeam: (teamId: number) =>
      `team knowledge base · team #${teamId}`,
    activeTaskTitle: "Active task",
    activeTaskDescription:
      "This panel polls the most recent task triggered from the workspace."
  },
  documents: {
    chooseFileError: "Choose a .txt, .md, .pdf, .docx, .mp3, .wav, .m4a, .mp4, .mov, .m4v, .png, .jpg, or .jpeg file first.",
    unsupportedFileType: "Only .txt, .md, .pdf, .docx, .mp3, .wav, .m4a, .mp4, .mov, .m4v, .png, .jpg, and .jpeg files are currently supported in the product UI.",
    supportedFormats: "Supported formats: .txt, .md, .pdf, .docx, .mp3, .wav, .m4a, .mp4, .mov, .m4v, .png, .jpg, .jpeg",
    uploadSubmit: "Upload document",
    uploading: "Uploading...",
    uploadFailed: "Upload failed.",
    uploadSucceeded: (filename: string) =>
      `${filename} was uploaded successfully.`,
    uploadSubmittedForReview: (filename: string) =>
      `${filename} was uploaded and submitted for review.`,
    uploadProcessingStarted: (filename: string) =>
      `${filename} was uploaded. PureLink is preparing it for search and Q&A.`,
    processingSubmitted: (filename: string) =>
      `${filename} was queued for background processing. Refresh in a moment to see the latest status.`,
    uploadReady: (filename: string) =>
      `${filename} is ready for search and Q&A.`,
    uploadedAt: "Uploaded",
    reviewComment: "Review comment",
    processStart: "Start processing",
    processContinue: "Continue processing",
    processRetry: "Retry processing",
    processingNow: "Processing",
    processingSuccess: "Ready",
    processingFailed: "Processing failed",
    processingTimeout:
      "Processing took too long. Check the document again in a moment.",
    statusAvailable: "Ready for search",
    statusAvailableHint:
      "This document is available for search and question answering.",
    statusPendingReview: "Waiting for review",
    statusPendingReviewHint:
      "A team admin must approve this document before it becomes part of the knowledge base.",
    statusRejected: "Needs changes",
    statusRejectedHint:
      "This document was not approved. Review the comment and upload an updated version.",
    statusUploaded: "Uploaded",
    statusUploadedHint:
      "The document is in the knowledge base and can be prepared for search.",
    statusProcessing: "Processing",
    statusProcessingHint:
      "PureLink is preparing this document for search and Q&A.",
    statusFailed: "Processing failed",
    statusFailedHint:
      "Something went wrong while preparing this document. Try again.",
    statusUnsupported: "Unsupported format",
    statusUnsupportedHint:
      "This document cannot be prepared from the current UI because only .txt, .md, .pdf, .docx, .mp3, .wav, .m4a, .mp4, .mov, .m4v, .png, .jpg, and .jpeg are supported.",
    statusReadyToContinue: "Ready to continue",
    statusReadyToContinueHint:
      "The document was partially prepared and can continue to the final step."
  },
  qa: {
    retrieveTitle: "Retrieve context",
    retrieveDescription: (scopeLabel: string) =>
      `Find the most relevant content from this knowledge base before asking. Current scope: ${scopeLabel}.`,
    retrieveQuery: "Query",
    retrieveTopK: "Top K",
    retrieveSubmit: "Retrieve",
    retrieving: "Retrieving...",
    retrieveFailed: "Retrieval failed.",
    askTitle: "Ask PureLink",
    askDescription:
      "Ask questions about this knowledge base. Relevant excerpts stay visible in the side panel.",
    askQuestion: "Question",
    askTopK: "Top K",
    askSubmit: "Ask",
    asking: "Answering...",
    askFailed: "Ask failed.",
    answerTitle: "Answer",
    citationsTitle: "Citations",
    citationsDescription:
      "Relevant document excerpts for the current answer stay visible here.",
    citationsEmpty:
      "No citations yet. Run retrieval or ask a question.",
    citationPage: (page: number) => `Page ${page}`,
    citationSection: (section: string) => `Section ${section}`,
    citationHeadingPath: (path: string) => `Heading ${path}`,
    citationCharRange: (start: number, end: number) => `Characters ${start}-${end}`,
    citationImageRegion: "OCR text region",
    citationTimeRange: (start: string, end: string) => `${start} - ${end}`,
    citationScore: (score: number) => `Score ${score.toFixed(3)}`,
    openConversation: (id: number) => `Open conversation #${id}`
  },
  teams: {
    pageTitle: "My teams",
    pageDescription:
      "Teams expose collaboration, reviews, and shared knowledge bases.",
    pageLoading: "Loading teams...",
    pageLoadError: "Unable to load teams.",
    pageEmpty: "No teams yet. Create one or join with an invite code.",
    createTitle: "Create team",
    createDescription:
      "Start a shared workspace and become its first admin.",
    createError: "Unable to create team.",
    createSubmit: "Create team",
    creating: "Creating...",
    joinTitle: "Join by invite",
    joinDescription:
      "Paste an invite code from a team admin to join.",
    joinError: "Unable to join team.",
    joinSubmit: "Join team",
    joining: "Joining...",
    openTeam: "Open team",
    roleAdmin: "Admin",
    roleMember: "Member",
    detailLabel: "Team workspace",
    loadingTeam: "Loading team...",
    reviewsLink: "Open review queue",
    membersTitle: "Team members",
    membersDescription:
      "Everyone with active membership in this team.",
    inviteTitle: "Invite teammates",
    inviteDescription:
      "Create invite codes that new members can use.",
    expiresInDays: "Expires in days",
    inviteError: "Unable to create invite.",
    teamKnowledgeBasesTitle: "Team knowledge bases",
    teamKnowledgeBasesDescription:
      "Shared knowledge workspaces for approved team content.",
    teamKnowledgeBasesEmpty: "No team knowledge bases yet.",
    createKbTitle: "New team knowledge base",
    createKbDescription:
      "Admins control the shared knowledge structure for this team.",
    permissionsTitle: "Permissions",
    permissionsBody:
      "You can access team knowledge bases and submit documents, but only admins can create invites, team knowledge bases, and review team documents."
  },
  reviews: {
    label: "Review queue",
    title: "Pending team documents",
    description:
      "Only team admins can approve or reject submitted documents. Approved documents can then be prepared for search and Q&A.",
    approvalNote:
      "Approval changes the review result only. The document still needs to be prepared before it becomes searchable.",
    rejectReason: "Rejection reason",
    rejectSubmit: "Reject",
    rejecting: "Rejecting...",
    rejectError: "Unable to reject document.",
    approveSubmit: "Approve",
    approving: "Approving...",
    empty: "No pending review tasks."
  },
  conversations: {
    pageLabel: "Conversation history",
    pageTitle: "Saved Q&A sessions",
    pageDescription:
      "Conversations are persisted from the ask flow and stay linked to the underlying knowledge base.",
    loading: "Loading conversations...",
    emptyTitle: "No conversations yet",
    emptyBody:
      "Ask questions from a knowledge base to start building message history.",
    openConversation: "Open conversation",
    summaryLabel: "Conversation summary",
    messagesTitle: "Messages",
    messagesDescription:
      "Stored user and assistant messages, including citations.",
    notFound: "Conversation not found",
    loadingSingle: "Loading conversation..."
  }
};

export type Messages = typeof en;
