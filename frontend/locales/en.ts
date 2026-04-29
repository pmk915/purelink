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
    processing: "preparing",
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
    taskId: (id: number) => `Activity #${id}`,
    expires: "Expires",
    submittedBy: (id: number) => `Submitted by user #${id}`,
    chunk: (id: string) => `Source excerpt ${id}`,
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
      "No teams yet. Create one to start shared knowledge work.",
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
      "The Core build supports .txt, .md, and text-based .pdf files. After upload, PureLink prepares them for search and Q&A automatically.",
    uploadDescriptionTeam:
      "The Core build supports .txt, .md, and text-based .pdf files. Admin uploads are prepared automatically; member uploads wait for review.",
    documentsTitle: "Documents",
    documentsDescription:
      "Track document status while PureLink advances upload, review, and preparation automatically.",
    noDocuments: "No documents yet.",
    workspaceScopePersonal: "personal knowledge base",
    workspaceScopeTeam: (teamId: number) =>
      `team knowledge base · team #${teamId}`,
    activeTaskTitle: "Background activity",
    activeTaskDescription:
      "This panel follows the latest background activity from the workspace."
  },
  documents: {
    chooseFileError: "Choose a .txt, .md, or .pdf file first.",
    unsupportedFileType: "This Core build focuses on text knowledge bases and currently supports only .txt, .md, and .pdf files.",
    supportedFormats: "Supported formats: .txt, .md, .pdf",
    uploadSubmit: "Upload document",
    uploading: "Uploading...",
    uploadFailed: "Upload failed.",
    uploadStatuses: {
      uploading: "Uploading",
      queued: "Queued",
      processing: "Preparing",
      indexed: "Ready",
      failed: "Failed",
      duplicate: "Duplicate",
      too_large: "Too large"
    },
    uploadSucceeded: (filename: string) =>
      `${filename} was uploaded successfully.`,
    uploadSubmittedForReview: (filename: string) =>
      `${filename} was uploaded and submitted for review.`,
    uploadProcessingStarted: (filename: string) =>
      `${filename} was uploaded. PureLink is preparing it for search and Q&A.`,
    processingSubmitted: (filename: string) =>
      `${filename} is being prepared. Refresh in a moment to see the latest status.`,
    uploadReady: (filename: string) =>
      `${filename} is ready for search and Q&A.`,
    uploadedAt: "Uploaded",
    reviewComment: "Review comment",
    processRetry: "Retry",
    processingNow: "Preparing",
    processingSuccess: "Ready for Q&A",
    processingFailed: "Preparation failed",
    processingFailedHelp:
      "The file could not be prepared. Try again or contact an admin.",
    processingTimeout:
      "Preparation is taking longer than expected. Check the document again in a moment.",
    statusAvailable: "Ready for Q&A",
    statusAvailableHint:
      "This document is available for search and question answering.",
    statusPendingReview: "Waiting for review",
    statusPendingReviewHint:
      "A team admin must approve this document before it becomes part of the knowledge base.",
    statusRejected: "Review rejected",
    statusRejectedHint:
      "This document was not approved. Review the comment and upload an updated version.",
    statusUploaded: "Uploaded",
    statusUploadedHint:
      "The document is in the knowledge base and will be prepared automatically.",
    statusProcessing: "Preparing",
    statusProcessingHint:
      "PureLink is preparing this document for search and Q&A.",
    statusFailed: "Preparation failed",
    statusFailedHint:
      "The file could not be prepared. Try again or contact an admin.",
    failureHints: {
      PDF_TEXT_GARBLED:
        "PDF text extraction looked abnormal. This may be a scanned or specially encoded PDF.",
      OCR_PROVIDER_UNAVAILABLE:
        "OCR is not available. Check the local OCR dependency.",
      OCR_NO_TEXT_FOUND:
        "No useful text could be recognized from this file.",
      TEXT_QUALITY_TOO_LOW:
        "The file content quality is too low to use for Q&A right now.",
      CHUNK_PERSIST_FAILED:
        "Document chunks could not be saved. Try again.",
      FEATURE_NOT_ENABLED:
        "This capability is not enabled in the current Core build.",
      UNSUPPORTED_FILE_TYPE:
        "This Core build focuses on text knowledge bases and does not support this file type."
    },
    statusUnsupported: "Unsupported format",
    statusUnsupportedHint:
      "This Core build focuses on text knowledge bases and supports only .txt, .md, and text-based .pdf files.",
    statusReadyToContinue: "Ready to continue",
    statusReadyToContinueHint:
      "The document was partially prepared and can continue to the final step.",
    previewBack: "Back to workspace",
    previewTitle: "Source preview",
    previewLoading: "Loading source preview...",
    previewError: "Unable to load source preview.",
    previewNoChunks: "No source excerpts are available for this document.",
    previewLocation: "Location",
    previewSnippet: "Source excerpt",
    previewExtractedText: "Extracted text",
    previewPdfPage: (page: number) => `PDF page ${page}`,
    previewImageRegion: "OCR text region",
    previewMediaRange: (range: string) => `Time range ${range}`,
    previewOriginalImageAlt: (filename: string) => `Original image for ${filename}`,
    previewFileUnavailable: "Original preview is not available for this file."
  },
  qa: {
    askTitle: "Ask PureLink",
    askDescription:
      "Ask questions about this knowledge base. Supporting sources stay visible in the side panel.",
    askQuestion: "Question",
    askSubmit: "Ask",
    asking: "Answering...",
    askFailed: "Unable to generate an answer right now. Try again or contact an admin.",
    answerTitle: "Answer",
    citationsTitle: "Sources",
    citationsDescription:
      "Supporting source excerpts for the current answer stay visible here.",
    citationsEmpty:
      "Citations will appear here after you ask a question.",
    noQueryableDocuments:
      "This knowledge base has no Q&A-ready documents yet. Upload a file first.",
    documentsWaitingReview:
      "Documents are waiting for review. You can ask questions after approval and preparation finish.",
    documentsPreparing:
      "Documents are being prepared. You can ask questions after preparation finishes.",
    noAvailableDocuments:
      "No documents are currently available for Q&A. Check document status or upload another file.",
    noReliableSources:
      "PureLink did not find enough reliable source material. Try another question or add relevant documents.",
    citationPage: (page: number) => `Page ${page}`,
    citationSection: (section: string) => `Section ${section}`,
    citationHeadingPath: (path: string) => `Heading ${path}`,
    citationCharRange: (start: number, end: number) => `Characters ${start}-${end}`,
    citationImageRegion: "OCR text region",
    citationTimeRange: (start: string, end: string) => `${start} - ${end}`,
    citationScore: (score: number) => `Score ${score.toFixed(3)}`,
    citationViewSource: "View source",
    openConversation: (id: number) => `Open conversation #${id}`
  },
  teams: {
    pageTitle: "My teams",
    pageDescription:
      "Teams expose collaboration, reviews, and shared knowledge bases.",
    pageLoading: "Loading teams...",
    pageLoadError: "Unable to load teams.",
    pageEmpty: "No teams yet. Create one to start a shared workspace.",
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
    reviewSummaryTitle: "Review queue",
    reviewSummaryDescription: (count: number) =>
      count === 1 ? "1 document needs admin review." : `${count} documents need admin review.`,
    membersTitle: "Team members",
    membersDescription:
      "Everyone with active membership in this team.",
    inviteTitle: "Invite teammates",
    inviteDescription:
      "Create invite codes that new members can use.",
    inviteEmpty: "No active invite codes.",
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
      "Approval starts preparation automatically. No extra step is needed.",
    rejectReason: "Rejection reason",
    rejectSubmit: "Reject",
    rejecting: "Rejecting...",
    rejectError: "Unable to reject document.",
    approveSubmit: "Approve",
    approving: "Approving...",
    approveError: "Unable to approve document.",
    autoPrepareError:
      "The document was approved, but automatic preparation did not start. Retry from the document list or contact an admin.",
    empty: "No pending review tasks."
  },
  conversations: {
    pageLabel: "Conversation history",
    pageTitle: "Saved Q&A sessions",
    pageDescription:
      "Conversations are saved after you ask and stay linked to the related knowledge base.",
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
