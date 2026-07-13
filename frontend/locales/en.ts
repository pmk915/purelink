export const en = {
  common: {
    loadingWorkspace: "Loading PureLink workspace...",
    loading: "Loading...",
    somethingWentWrong: "Something went wrong",
    permissionDenied: "Permission denied",
    notFound: "Not found",
    tryAgain: "Try again",
    requestId: "Request ID",
    errorCode: "Error code",
    noDocumentsYet: "No documents yet",
    noGraphDataYet: "No graph data yet",
    noMatchingResults: "No matching results",
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
    cancel: "Cancel",
    delete: "Delete",
    deleting: "Deleting...",
    copy: "Copy",
    copied: "Copied",
    yes: "Yes",
    no: "No",
    anonymous: "Anonymous",
    openNavigation: "Open navigation",
    review: "review",
    processing: "preparing",
    status: "Status",
    personal: "Personal",
    personalKnowledgeBase: "Personal knowledge base",
    team: "Team",
    teamKnowledgeBase: "Team knowledge base",
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
      "The Core build supports .txt, .md, .docx, and text-based .pdf files. After upload, PureLink prepares them for search and Q&A automatically.",
    uploadDescriptionTeam:
      "The Core build supports .txt, .md, .docx, and text-based .pdf files. Admin uploads are prepared automatically; member uploads wait for review.",
    askTab: "Q&A",
    documentsTab: "Documents",
    graphTab: "Graph",
    retrievalDebugTab: "Retrieval Debug",
    healthTab: "Health",
    settingsTab: "Settings",
    settingsDescription:
      "Review knowledge base metadata and safe management actions.",
    embeddingChangeWarning:
      "Changing embedding providers or models requires rebuilding affected document indexes.",
    documentsTitle: "Documents",
    documentsDescription:
      "Track document status while PureLink advances upload, review, and preparation automatically.",
    documentsSummaryTitle: "Document status",
    documentsSummaryDescription:
      "Uploads, preparation, and retry actions stay in one place.",
    viewAllDocuments: "View all documents",
    recentConversationsTitle: "Recent conversations",
    recentConversationsDescription:
      "Questions started from this knowledge base appear here.",
    recentConversationsEmpty:
      "No conversations for this knowledge base yet. Ask a question to create one.",
    qaEmptyState:
      "This knowledge base has no documents yet. Upload a txt, md, docx, or text-based PDF first.",
    qaPreparingState:
      "Documents are being prepared. You can ask after processing finishes.",
    qaWaitingReviewState:
      "Some documents are still waiting for review before they can be used in Q&A.",
    qaUnavailableState:
      "No askable documents are available yet. Check failed documents or upload more content.",
    qaReadyState:
      "This knowledge base already has Q&A-ready documents. You can start asking now.",
    noDocuments: "No documents yet.",
    deleteDialogTitle: "Delete knowledge base?",
    deleteDialogDescription: (name: string) =>
      `This will delete “${name}” with its documents, indexes, and answer source data. This cannot be undone.`,
    deleteTeamDialogDescription: (name: string) =>
      `Deleting team knowledge base “${name}” affects team member access to its documents and answers. This cannot be undone.`,
    deleteSucceeded: (name: string) => `Knowledge base “${name}” was deleted.`,
    deleteFailed: "Knowledge base delete failed. Please try again.",
    deleteAdminOnly: "Only team admins can delete team knowledge bases.",
    ragHealthTitle: "Knowledge base health",
    ragHealthDescription:
      "Document processing, vector index, and graph index summary.",
    healthDocuments: "Documents",
    healthVectorIndex: "Vector index",
    healthGraphIndex: "Graph index",
    healthIndexed: "Indexed",
    healthFailed: "Failed",
    healthMissing: "Missing",
    healthStale: "Stale",
    workspaceScopePersonal: "personal knowledge base",
    workspaceScopeTeam: (teamId: number) =>
      `team knowledge base · team #${teamId}`,
    activeTaskTitle: "Background activity",
    activeTaskDescription:
      "This panel follows the latest background activity from the workspace."
  },
  documents: {
    chooseFileError: "Choose a .txt, .md, .docx, or .pdf file first.",
    unsupportedFileType: "This Core build focuses on text knowledge bases and currently supports only .txt, .md, .docx, and .pdf files.",
    supportedFormats: "Supported formats: .txt, .md, .docx, .pdf",
    supportedFormatsWithLimit: (formats: string, maxSizeMb: number) =>
      `Supports ${formats} up to ${maxSizeMb} MB.`,
    unsupportedFileTypeWithFormats: (formats: string) =>
      `Unsupported file type. Please upload ${formats}.`,
    fileTooLarge: (maxSizeMb: number) =>
      `This file is too large. The maximum size is ${maxSizeMb} MB.`,
    emptyFile: "The selected file is empty.",
    invalidFileName: "Invalid file name.",
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
      too_large: "Too large",
      unsupported: "Unsupported"
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
    deleteDialogTitle: "Delete file?",
    deleteDialogDescription: (filename: string) =>
      `This will delete “${filename}” and remove it from the knowledge base index.`,
    deleteSucceeded: (filename: string) => `${filename} was deleted.`,
    deleteFailed: "Delete failed. Please try again.",
    onlyTeamAdminsOrOwnersCanDelete: "Only team admins or the document owner can delete files.",
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
      "This Core build focuses on text knowledge bases and supports only .txt, .md, .docx, and text-based .pdf files.",
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
    previewFileUnavailable: "Original preview is not available for this file.",
    viewStatus: "View status",
    statusDialogTitle: "Document status",
    statusDialogDescription:
      "This panel shows whether the document has completed the retrieval pipeline.",
    ragReady: "RAG ready",
    notReady: "Not ready",
    copyDebugInfo: "Copy debug info",
    debugInfo: "Debug info",
    overview: "Overview",
    pipeline: "Pipeline checks",
    warningsAndErrors: "Warnings and errors",
    noWarnings: "No warnings found.",
    possibleReasons: "Possible reasons",
    latestStep: "Latest step",
    errorCode: "Error code",
    errorMessage: "Error message",
    lastIndexed: "Last indexed",
    vectorIndex: "Vector index",
    graphIndex: "Graph index",
    blocks: "Blocks",
    chunks: "Chunks",
    citations: "Citations",
    entities: "Entities",
    relations: "Relations",
    statusLoadError: "Unable to load document status.",
    diagnosticsMissing: "Diagnostics are not available yet.",
    copiedDebugInfo: "Copied",
    statusLabel: (status: string) =>
      ({
        ready: "Ready",
        missing: "Missing",
        warning: "Warning",
        failed: "Failed",
        optional: "Optional",
        pending: "Pending",
        uploaded: "Uploaded",
        processing: "Processing",
        parsed: "Parsed",
        indexed: "Indexed"
      })[status] ?? status
  },
  processingJobs: {
    title: "Processing jobs",
    description:
      "Inspect document preparation jobs, failure details, and retry eligible documents.",
    refresh: "Refresh",
    loading: "Loading processing jobs...",
    loadError: "Unable to load processing jobs.",
    emptyTitle: "No processing jobs yet",
    emptyDescription:
      "Upload a document to create the first background preparation job.",
    all: "All",
    running: "Running",
    runningHint: "Queued or active jobs",
    failed: "Failed",
    failedHint: "Jobs that need attention",
    completed: "Completed",
    completedHint: "Finished jobs",
    searchPlaceholder: "Search documents...",
    currentStep: "Step",
    latestJob: "Latest processing job",
    retry: "Retry",
    retrySubmitted: (filename: string) =>
      `${filename} was queued for processing retry.`,
    retryFailed: "Retry failed. Check permissions or job state.",
    adminOnly: "Admin only",
    attemptCount: (attempt: number, max: number) => `Attempt ${attempt}/${max}`,
    statusLabel: (status: string) =>
      ({
        queued: "Queued",
        processing: "Processing",
        retrying: "Retrying",
        succeeded: "Succeeded",
        failed: "Failed",
        cancelled: "Cancelled"
      })[status] ?? status,
    jobTypeLabel: (jobType: string) =>
      ({
        document_process: "Document process",
        document_index: "Document index"
      })[jobType] ?? jobType
  },
  qa: {
    askTitle: "Ask PureLink",
    askDescription:
      "Start with a question here, then continue in the full conversation view with citations.",
    askQuestion: "Question",
    askPlaceholder: "Ask this knowledge base...",
    suggestedQuestions: "Suggested questions",
    suggestionSummary: "Based on the documents, describe the core subject in this knowledge base",
    suggestionKeyPoints: "What facts are explicitly stated in these documents?",
    suggestionUseKnowledgeBase: "Answer a concrete question using the uploaded documents",
    askSubmit: "Ask",
    asking: "Answering...",
    askFailed: "Failed to retrieve answer.",
    answerTitle: "Answer",
    citationsTitle: "Sources",
    citationsDescription:
      "Supporting source excerpts for the current answer stay visible here.",
    citationsEmpty:
      "Citations will appear here after you ask a question.",
    noQueryableDocuments:
      "This knowledge base has no Q&A-ready documents yet. Upload a file first.",
    noQueryablePersonalKnowledgeBase:
      "This personal knowledge base does not have any askable documents yet. Upload documents and wait for processing to finish.",
    noQueryableTeamKnowledgeBase:
      "This team knowledge base does not have any askable documents yet. Documents may still be under review or processing.",
    documentsWaitingReview:
      "Documents are waiting for review. You can ask questions after approval and preparation finish.",
    documentsPreparing:
      "Documents are being prepared. You can ask questions after preparation finishes.",
    documentsReadyButNotIndexed:
      "Documents finished processing but are not in the askable index yet. Refresh in a moment or reindex the knowledge base.",
    documentsNeedReindex:
      "Some documents in this knowledge base have not finished indexing. Reindexing the knowledge base may be required before Q&A works normally.",
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
    citationTitle: (number: string) => `Citation ${number}`,
    viewCitationAria: (number: string, documentName: string) =>
      `View citation ${number}: ${documentName}`,
    closeCitation: "Close citation",
    citationNavigation: "Citations in this answer",
    sourceDetails: "Source details",
    quotedEvidence: "Quoted evidence",
    technicalDetails: "Technical details",
    citationReady: "Citation ready",
    evidenceScore: "Evidence score",
    sourceLocation: "Source location",
    sourceType: "Source type",
    section: "Section",
    headingPath: "Heading path",
    page: "Page",
    characterRange: "Character range",
    limitedSourceDetails: "Source details are limited for this citation.",
    citationUnknownDocument: "Unknown document",
    finalEvidenceNote: "This is the final evidence excerpt cited by the answer.",
    evidenceSnippet: "Evidence snippet",
    retrievalDetails: "Retrieval details",
    retrievalDetailsDescription:
      "This shows citation/evidence data currently available to the frontend. Fields such as trace_id will appear when the backend response exposes them.",
    evidenceCount: (count: number) => `Evidence count: ${count}`,
    retrievalMode: "Retrieval mode",
    selectedRetrievalMode: "System selected",
    routerReason: "Reason",
    retrievalModeLabel: (mode: string) =>
      ({
        auto: "Auto",
        chunk_only: "Chunk retrieval",
        overview: "Overview retrieval",
        graph_vector_mix: "Graph + vector hybrid",
        hybrid_text: "Keyword + vector hybrid"
      })[mode] ?? mode,
    usedReranker: "Used reranker",
    openConversation: (id: number) => `Open conversation #${id}`
  },
  graph: {
    title: "Knowledge graph",
    description:
      "Explore lightweight entities, mentions, and grounded relations extracted from this knowledge base.",
    searchPlaceholder: "Search entities...",
    search: "Search",
    refresh: "Refresh",
    loadError: "Unable to load graph data.",
    empty:
      "No graph data yet. Upload and index documents first; PureLink will attempt lightweight graph extraction after indexing.",
    detailTitle: "Entity detail",
    detailDescription: "Select an entity to inspect mentions and connected relations.",
    mentions: "Mentions",
    entities: "Entities",
    relations: "Relations",
    noMentions: "No mentions for this entity.",
    noRelations: "No relations for this entity.",
    noSourceLocator: "No source locator",
    noSourceDocument: "No source document",
    relationType: "Relation type",
    relationTypes: "Relation types",
    allRelationTypes: "All relation types",
    allEntities: "All entities",
    showingAll: "Showing graph export",
    selectedEntity: "Selected entity",
    oneHopNeighborhood: "One-hop neighborhood",
    entityListDescription: "Search entities or select one to inspect direct graph neighbors.",
    relationListDescription: "Inspect grounded relations and their source evidence.",
    summaryEntities: "Entities",
    summaryRelations: "Relations",
    clearSelection: "Clear selection",
    exportJson: "Export JSON",
    exportEntitiesCsv: "Entities CSV",
    exportRelationsCsv: "Relations CSV",
    sourceCount: (count: number) => `${count} source${count === 1 ? "" : "s"}`,
    viewSources: "View sources",
    relationSources: "Relation sources",
    noSources: "No sources recorded for this relation.",
    viewDocumentStatus: "View document status",
    chunk: "Chunk",
    noChunk: "No chunk",
    citationUnit: "Citation unit",
    filteredCount: (count: number) => `${count} after filters`,
    entityStats: (mentions: number, relations: number) =>
      `${mentions} mentions · ${relations} relations`
  },
  retrievalDebug: {
    title: "Retrieval Debug",
    description:
      "Run retrieval directly to inspect candidates before answer generation.",
    query: "Query",
    queryPlaceholder: "Test a retrieval query...",
    mode: "Mode",
    hybridTextMode: "Keyword + vector hybrid",
    run: "Run retrieval",
    running: "Retrieving...",
    failed: "Retrieval failed. Check query, mode, or permissions."
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
    newConversation: "New conversation",
    newConversationTitle: "What do you want to ask today?",
    newConversationDescription:
      "Pick a knowledge base you can access, then start asking.",
    recentTitle: "Recent conversations",
    moreActions: "More actions",
    currentKnowledgeBase: "Current knowledge base",
    readyWhenYouAre: "Ready when you are",
    noMessagesYet: "No messages yet. Start by asking this knowledge base.",
    viewSources: (count: number) => `View sources ${count}`,
    hideSources: (count: number) => `Hide sources ${count}`,
    selectKnowledgeBase: "Choose a knowledge base",
    selectKnowledgeBaseHint:
      "Select a knowledge base before you send your first question.",
    noKnowledgeBasesAvailable:
      "No knowledge bases are available for this account yet. Create one or join a team first.",
    loading: "Loading conversations...",
    emptyTitle: "No conversations yet",
    emptyBody:
      "Ask questions from a knowledge base to start building message history.",
    openConversation: "Open conversation",
    summaryLabel: "Conversation summary",
    messagesTitle: "Messages",
    messagesDescription:
      "Stored user and assistant messages, including citations.",
    deleteDialogTitle: "Delete chat?",
    deleteDialogDescription: (title: string) => `This will delete “${title}”.`,
    deleteFailed: "Delete failed. Please try again.",
    notFound: "Conversation not found",
    loadingSingle: "Loading conversation..."
  }
};

export type Messages = typeof en;
