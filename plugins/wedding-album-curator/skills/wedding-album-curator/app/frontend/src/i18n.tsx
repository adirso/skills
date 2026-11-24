import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Lang = "en" | "he";

const STRINGS: Record<string, { en: string; he: string }> = {
  appName: { en: "Wedding Album Curator", he: "אוצר אלבום החתונה" },
  tagline: { en: "Choose your album photos calmly — with an assistant that explains itself.", he: "בוחרים תמונות לאלבום בנחת — עם עוזר שמסביר כל המלצה." },
  // nav
  dashboard: { en: "Overview", he: "סקירה" },
  library: { en: "Library", he: "ספרייה" },
  people: { en: "People", he: "אנשים" },
  compare: { en: "Compare", he: "השוואה" },
  album: { en: "Album Builder", he: "בניית אלבום" },
  review: { en: "Review Queue", he: "תור בדיקה" },
  export: { en: "Export", he: "ייצוא" },
  settings: { en: "AI & Privacy", he: "בינה מלאכותית ופרטיות" },
  projects: { en: "Projects", he: "פרויקטים" },
  // generic
  cancel: { en: "Cancel", he: "ביטול" },
  continue: { en: "Continue", he: "המשך" },
  back: { en: "Back", he: "חזרה" },
  save: { en: "Save", he: "שמירה" },
  close: { en: "Close", he: "סגירה" },
  loading: { en: "Loading…", he: "טוען…" },
  pause: { en: "Pause", he: "השהיה" },
  resume: { en: "Resume", he: "המשך" },
  stop: { en: "Stop", he: "עצירה" },
  photos: { en: "photos", he: "תמונות" },
  of: { en: "of", he: "מתוך" },
  none: { en: "None", he: "ללא" },
  delete: { en: "Delete", he: "מחיקה" },
  yes: { en: "Yes", he: "כן" },
  no: { en: "No", he: "לא" },
  error: { en: "Something went wrong", he: "משהו השתבש" },
  // projects / onboarding
  newProject: { en: "New wedding project", he: "פרויקט חתונה חדש" },
  openProject: { en: "Open", he: "פתיחה" },
  noProjects: { en: "No projects yet. Start by choosing the folder your photographer sent you.", he: "אין עדיין פרויקטים. מתחילים בבחירת התיקייה שהצלם שלח לכם." },
  welcomeTitle: { en: "Let’s build your wedding album", he: "בואו נבנה את אלבום החתונה שלכם" },
  welcomeBody: {
    en: "This app runs on your computer. Your photos stay here, the originals are never changed, and you make every final decision.",
    he: "האפליקציה פועלת על המחשב שלכם. התמונות נשארות אצלכם, קובצי המקור לעולם אינם משתנים, וכל החלטה סופית היא שלכם.",
  },
  projectName: { en: "Project name", he: "שם הפרויקט" },
  projectNamePh: { en: "e.g. Noa & Daniel", he: "למשל: נועה ודניאל" },
  chooseFolder: { en: "Choose photo folder", he: "בחירת תיקיית תמונות" },
  browse: { en: "Browse…", he: "עיון…" },
  folderPath: { en: "Folder path", he: "נתיב התיקייה" },
  folderHint: { en: "The folder is read recursively. Nothing in it will be modified.", he: "התיקייה נסרקת כולל תתי-תיקיות. דבר בה לא ישתנה." },
  photosFound: { en: "{n} photos found", he: "נמצאו {n} תמונות" },
  checkFolder: { en: "Check folder", he: "בדיקת התיקייה" },
  stepWelcome: { en: "Welcome", he: "ברוכים הבאים" },
  stepFolder: { en: "Folder", he: "תיקייה" },
  stepAI: { en: "AI method", he: "שיטת AI" },
  stepHardware: { en: "This computer", he: "המחשב שלכם" },
  stepPrivacy: { en: "Privacy", he: "פרטיות" },
  stepStart: { en: "Start", he: "התחלה" },
  startAnalysis: { en: "Start analysis", he: "התחלת ניתוח" },
  // providers
  aiChoiceTitle: { en: "How should photos be analyzed?", he: "איך לנתח את התמונות?" },
  aiLocal: { en: "Local AI (recommended)", he: "בינה מלאכותית מקומית (מומלץ)" },
  aiLocalBody: {
    en: "Faces, quality, similar shots and moments are analyzed on this computer. Optionally add a local vision-language model through Ollama. Nothing is uploaded.",
    he: "פנים, איכות, צילומים דומים ורגעים מנותחים על המחשב הזה. אפשר להוסיף מודל שפה-ראייה מקומי דרך Ollama. דבר לא מועלה.",
  },
  aiClaudeCode: { en: "Claude via Claude Code (experimental)", he: "Claude דרך Claude Code (ניסיוני)" },
  aiClaudeCodeBody: {
    en: "Uses your installed Claude Code in non-interactive mode for extra moment analysis. Slow; best for the shortlisted album photos.",
    he: "משתמש ב-Claude Code המותקן אצלכם במצב לא-אינטראקטיבי לניתוח רגעים נוסף. איטי; מתאים לתמונות שנבחרו לאלבום.",
  },
  aiApi: { en: "Claude API (pay per use)", he: "Claude API (תשלום לפי שימוש)" },
  aiApiBody: {
    en: "Uses your own Anthropic API key. You see a cost estimate first and can set a spending limit.",
    he: "משתמש במפתח ה-API שלכם מ-Anthropic. תראו הערכת עלות מראש ותוכלו להגדיר תקרת הוצאה.",
  },
  aiNoneNote: { en: "The core analysis is always local. Cloud analysis is optional and can be added later.", he: "הניתוח הבסיסי תמיד מקומי. ניתוח בענן הוא אופציונלי ואפשר להוסיף אותו בהמשך." },
  cloudWarningTitle: { en: "Before using Claude", he: "לפני השימוש ב-Claude" },
  iAgree: { en: "I understand and agree", he: "הבנתי ואני מסכים/ה" },
  consentGiven: { en: "Consent recorded", he: "ההסכמה נרשמה" },
  revokeConsent: { en: "Revoke consent", he: "ביטול הסכמה" },
  // hardware
  hardwareTitle: { en: "Your computer", he: "המחשב שלכם" },
  ram: { en: "Memory", he: "זיכרון" },
  gpu: { en: "Graphics", he: "מעבד גרפי" },
  accelerator: { en: "Acceleration", he: "האצה" },
  modelsTitle: { en: "Local models", he: "מודלים מקומיים" },
  modelsBody: {
    en: "These open models run on your computer. They are downloaded once, only with your approval, and verified by checksum.",
    he: "מודלים פתוחים אלה רצים על המחשב שלכם. הם יורדים פעם אחת, רק באישורכם, ונבדקים לפי חתימה.",
  },
  approveDownload: { en: "Approve & download ({size})", he: "אישור והורדה ({size})" },
  installed: { en: "Installed", he: "מותקן" },
  notInstalled: { en: "Not installed", he: "לא מותקן" },
  downloading: { en: "Downloading…", he: "מוריד…" },
  // privacy
  privacyTitle: { en: "Privacy promises", he: "התחייבויות פרטיות" },
  privacy1: { en: "Photos never leave this computer unless you explicitly start a cloud analysis.", he: "התמונות לא יוצאות מהמחשב אלא אם תתחילו במפורש ניתוח בענן." },
  privacy2: { en: "Original files are never modified, moved or deleted.", he: "קובצי המקור לעולם אינם משתנים, מועברים או נמחקים." },
  privacy3: { en: "Face data is stored only on this computer and can be deleted at any time.", he: "נתוני פנים נשמרים רק במחשב הזה וניתן למחוק אותם בכל עת." },
  privacy4: { en: "No analytics or telemetry.", he: "ללא איסוף נתוני שימוש." },
  // dashboard
  totalPhotos: { en: "Photos", he: "תמונות" },
  processed: { en: "Analyzed", he: "נותחו" },
  discoveredPeople: { en: "People found", he: "אנשים שזוהו" },
  suggested: { en: "Suggested", he: "הוצעו" },
  selected: { en: "Selected", he: "נבחרו" },
  rejected: { en: "Rejected", he: "נדחו" },
  target: { en: "Album target", he: "יעד לאלבום" },
  analysis: { en: "Analysis", he: "ניתוח" },
  runAnalysis: { en: "Analyze new photos", he: "ניתוח תמונות חדשות" },
  nextSteps: { en: "Next steps", he: "הצעדים הבאים" },
  stepIdentify: { en: "Identify the bride and groom", he: "סמנו מי החתן ומי הכלה" },
  stepCompare: { en: "Pick the best of similar shots", he: "בחרו את הטובה מבין תמונות דומות" },
  stepGenerate: { en: "Generate the album suggestion", he: "צרו הצעה לאלבום" },
  stepReview: { en: "Check photos with possible problems", he: "בדקו תמונות עם בעיות אפשריות" },
  stepExport: { en: "Export the final selection", he: "ייצאו את הבחירה הסופית" },
  missingSource: { en: "The photo folder is not available. Reconnect the drive to continue.", he: "תיקיית התמונות אינה זמינה. חברו מחדש את הכונן כדי להמשיך." },
  measured: { en: "Measured speed", he: "מהירות שנמדדה" },
  // library
  sortTime: { en: "Time taken", he: "זמן צילום" },
  sortQuality: { en: "Quality", he: "איכות" },
  sortScore: { en: "Album score", he: "ציון אלבום" },
  sortName: { en: "File name", he: "שם קובץ" },
  filterAll: { en: "All", he: "הכל" },
  filterUndecided: { en: "Undecided", he: "ללא החלטה" },
  filterInAlbum: { en: "In album", he: "באלבום" },
  favorites: { en: "Favorites", he: "מועדפים" },
  anyMoment: { en: "Any moment", he: "כל רגע" },
  anyIssue: { en: "Any quality", he: "כל איכות" },
  blurry: { en: "Blurry", he: "מטושטש" },
  exposureIssue: { en: "Exposure", he: "חשיפה" },
  closedEyes: { en: "Closed eyes", he: "עיניים עצומות" },
  select: { en: "Select", he: "בחירה" },
  reject: { en: "Reject", he: "דחייה" },
  clearDecision: { en: "Undecided", he: "ללא החלטה" },
  favorite: { en: "Favorite", he: "מועדף" },
  shortcuts: { en: "Keyboard: ←/→ navigate · P select · X reject · U undecided · F favorite · 1–5 rate · Z zoom · Esc close", he: "מקלדת: חיצים לניווט · P בחירה · X דחייה · U ללא החלטה · F מועדף · 1–5 דירוג · Z הגדלה · Esc סגירה" },
  noPhotos: { en: "No photos match these filters.", he: "אין תמונות שמתאימות לסינון." },
  whyThis: { en: "Why this photo", he: "למה התמונה הזו" },
  qualitySignals: { en: "Quality signals", he: "מדדי איכות" },
  sharpness: { en: "Sharpness", he: "חדות" },
  exposure: { en: "Exposure", he: "חשיפה" },
  contrast: { en: "Contrast", he: "ניגודיות" },
  noise: { en: "Low noise", he: "רעש נמוך" },
  composition: { en: "Composition", he: "קומפוזיציה" },
  technical: { en: "Overall technical", he: "טכני כולל" },
  moment: { en: "Moment", he: "רגע" },
  changeMoment: { en: "Change moment", he: "שינוי רגע" },
  facesInPhoto: { en: "People in this photo", he: "אנשים בתמונה" },
  eyesClosed: { en: "eyes closed", he: "עיניים עצומות" },
  eyesOpen: { en: "eyes open", he: "עיניים פקוחות" },
  similarShots: { en: "Similar shots", he: "צילומים דומים" },
  aiCaption: { en: "AI description", he: "תיאור AI" },
  unknownPerson: { en: "Unnamed", he: "ללא שם" },
  // people
  peopleIntro: {
    en: "Faces were grouped automatically. Groupings are probabilistic — please check them. Only you can say who is who.",
    he: "הפנים קובצו אוטומטית. הקיבוץ הוא הסתברותי — כדאי לבדוק. רק אתם יכולים לקבוע מי זה מי.",
  },
  bride: { en: "Bride", he: "כלה" },
  groom: { en: "Groom", he: "חתן" },
  setAsBride: { en: "This is the bride", he: "זו הכלה" },
  setAsGroom: { en: "This is the groom", he: "זה החתן" },
  clearRole: { en: "Clear role", he: "ניקוי תפקיד" },
  importance: { en: "Importance", he: "חשיבות" },
  name: { en: "Name", he: "שם" },
  merge: { en: "Merge selected", he: "מיזוג הנבחרים" },
  mergeHint: { en: "Select two or more people who are the same person, then merge.", he: "בחרו שני אנשים או יותר שהם אותו אדם, ואז מזגו." },
  notThisPerson: { en: "Not this person", he: "לא האדם הזה" },
  moveToNew: { en: "Split into new person", he: "פיצול לאדם חדש" },
  confirmFaces: { en: "Confirm", he: "אישור" },
  markUncertain: { en: "Mark uncertain", he: "סימון כלא ודאי" },
  ignoreFace: { en: "Not a relevant face", he: "פנים לא רלוונטיות" },
  uncertainMatches: { en: "{n} uncertain", he: "{n} לא ודאיים" },
  hide: { en: "Hide", he: "הסתרה" },
  unhide: { en: "Show", he: "הצגה" },
  showPhotos: { en: "Photos", he: "תמונות" },
  regroup: { en: "Re-group faces", he: "קיבוץ פנים מחדש" },
  noPeople: { en: "No faces yet. Install the face models and run the analysis.", he: "אין עדיין פנים. התקינו את מודלי הפנים והריצו ניתוח." },
  facesPending: { en: "People were not searched in {n} photos (the face models were not installed when they were analyzed).", he: "לא חיפשנו אנשים ב-{n} תמונות (מודלי הפנים עוד לא היו מותקנים כשהן נותחו)." },
  facesPendingNoModels: { en: "Face models are not installed, so people cannot be found. Approve them in AI & Privacy.", he: "מודלי הפנים לא מותקנים, ולכן אי אפשר למצוא אנשים. אשרו אותם במסך בינה מלאכותית ופרטיות." },
  regroupHint: { en: "Quick: regroup the faces already found (seconds).", he: "מהיר: קיבוץ מחדש של הפנים שכבר נמצאו (שניות)." },
  rescanFaces: { en: "Re-scan faces", he: "סריקת פנים מחדש" },
  rescanStart: { en: "Re-scan all photos", he: "סריקה מחדש של כל התמונות" },
  rescanExplain: { en: "Detects every face again in all photos and regroups them. It takes a few minutes and runs in the background. Names, the bride and groom, importance, merges and your face corrections are kept. Your photos are not changed.", he: "מזהה מחדש את כל הפנים בכל התמונות ומקבץ אותן מחדש. זה לוקח כמה דקות ורץ ברקע. שמות, הכלה והחתן, רמות חשיבות, איחודים ותיקוני הפנים שלכם נשמרים. התמונות שלכם לא משתנות." },
  resetDefaults: { en: "Reset to our defaults", he: "חזרה להגדרות ברירת המחדל שלנו" },
  resetDefaultsHint: { en: "Restores the recommended moment shares, weights and variety settings. Your album size is kept. Click Generate to apply.", he: "מחזיר את חלוקת הרגעים, המשקלים והגיוון המומלצים. גודל האלבום שלכם נשמר. לחצו על יצירה כדי להחיל." },
  usingOurDefaults: { en: "Using our recommended settings", he: "בשימוש: ההגדרות המומלצות שלנו" },
  customSettings: { en: "Custom settings", he: "הגדרות מותאמות אישית" },
  nPhotos: { en: "{n} photos", he: "{n} תמונות" },
  availableInMoment: { en: "{n} available", he: "{n} זמינות" },
  lastAlbumGot: { en: "last album: {n}", he: "באלבום האחרון: {n}" },
  findPeopleNow: { en: "Find people now", he: "חיפוש אנשים עכשיו" },
  coupleMissing: { en: "Please mark the bride and the groom — the album depends on it.", he: "סמנו בבקשה את הכלה ואת החתן — האלבום תלוי בזה." },
  facesSelected: { en: "{n} faces selected", he: "{n} פנים נבחרו" },
  moveTo: { en: "Move to…", he: "העברה אל…" },
  importanceLevels: { en: "Importance levels", he: "רמות חשיבות" },
  weight: { en: "Weight", he: "משקל" },
  // compare
  compareIntro: { en: "Near-identical shots side by side. Keep the best; the others stay available.", he: "צילומים כמעט זהים זה לצד זה. בחרו את הטוב ביותר; האחרים נשארים זמינים." },
  recommended: { en: "Recommended", he: "מומלץ" },
  keepThis: { en: "Keep this one", he: "לשמור את זו" },
  rejectOthers: { en: "Reject the others", he: "לדחות את האחרות" },
  skipGroup: { en: "Skip", he: "דילוג" },
  onlyCouple: { en: "Bride & groom only", he: "רק חתן וכלה" },
  allGroups: { en: "All groups", he: "כל הקבוצות" },
  noGroups: { en: "No more similar groups to compare. 🎉", he: "אין עוד קבוצות דומות להשוואה. 🎉" },
  remainingGroups: { en: "{n} groups left", he: "נותרו {n} קבוצות" },
  // album
  generate: { en: "Generate recommendations", he: "יצירת המלצות" },
  regenerate: { en: "Regenerate (keeps your choices)", he: "יצירה מחדש (שומר את הבחירות שלכם)" },
  allocation: { en: "Moment allocation", he: "חלוקה לפי רגעים" },
  allocationHint: { en: "Suggestions, not hard rules.", he: "הצעות, לא כללים נוקשים." },
  weights: { en: "What matters most", he: "מה הכי חשוב" },
  wTechnical: { en: "Technical quality", he: "איכות טכנית" },
  wFaces: { en: "Clear faces", he: "פנים ברורות" },
  wPeople: { en: "Important people", he: "אנשים חשובים" },
  wMoment: { en: "Key moments", he: "רגעים מרכזיים" },
  wPreference: { en: "Your taste", he: "הטעם שלכם" },
  wRating: { en: "Your ratings", he: "הדירוגים שלכם" },
  lock: { en: "Lock", he: "נעילה" },
  locked: { en: "Locked", he: "נעול" },
  replace: { en: "Replace", he: "החלפה" },
  alternatives: { en: "Alternatives", he: "חלופות" },
  albumEmpty: { en: "No recommendation yet. Set the target and generate.", he: "אין עדיין המלצה. קבעו יעד וצרו המלצות." },
  shortfall: { en: "Shortfall", he: "חוסר" },
  coupleShare: { en: "Bride/groom share", he: "חלק החתן והכלה" },
  learnedTaste: { en: "Learned from your choices", he: "נלמד מהבחירות שלכם" },
  resetTaste: { en: "Reset learned preferences", he: "איפוס העדפות שנלמדו" },
  prefNone: { en: "Mark a few favorites to teach the assistant your taste.", he: "סמנו כמה מועדפות כדי ללמד את העוזר את הטעם שלכם." },
  bucket_getting_ready: { en: "Getting ready", he: "התארגנות" },
  bucket_couple: { en: "Couple", he: "הזוג" },
  bucket_family_friends: { en: "Family & friends", he: "משפחה וחברים" },
  bucket_ceremony: { en: "Ceremony", he: "טקס" },
  bucket_reception_dancing: { en: "Reception & dancing", he: "קבלת פנים וריקודים" },
  bucket_other: { en: "Other", he: "אחר" },
  // categories
  cat_getting_ready: { en: "Getting ready", he: "התארגנות" },
  cat_couple_portraits: { en: "Couple portraits", he: "צילומי זוג" },
  cat_family_portraits: { en: "Family portraits", he: "צילומי משפחה" },
  cat_friends: { en: "Friends", he: "חברים" },
  cat_ceremony: { en: "Ceremony", he: "טקס" },
  cat_rings: { en: "Rings", he: "טבעות" },
  cat_first_kiss: { en: "First kiss", he: "נשיקה ראשונה" },
  cat_first_dance: { en: "First dance", he: "ריקוד ראשון" },
  cat_reception: { en: "Reception", he: "קבלת פנים" },
  cat_party_dancing: { en: "Party & dancing", he: "מסיבה וריקודים" },
  cat_other: { en: "Other moments", he: "רגעים אחרים" },
  // review
  reviewIntro: { en: "Nothing is deleted. Decide for each photo, or mark it reviewed to keep it as is.", he: "שום דבר לא נמחק. החליטו לגבי כל תמונה, או סמנו שנבדקה כדי להשאיר אותה כמו שהיא." },
  markReviewed: { en: "Looks fine", he: "נראה בסדר" },
  queueEmpty: { en: "This queue is empty.", he: "התור הזה ריק." },
  // export
  exportIntro: { en: "Copies the approved photos at original quality into a new folder. Originals are not touched.", he: "מעתיק את התמונות שאושרו באיכות מקורית לתיקייה חדשה. לא נוגעים בקובצי המקור." },
  destination: { en: "Destination folder (new or empty)", he: "תיקיית יעד (חדשה או ריקה)" },
  subfolders: { en: "Create a subfolder per moment", he: "תת-תיקייה לכל רגע" },
  exportMode: { en: "What to export", he: "מה לייצא" },
  exportAlbum: { en: "Album: recommendations you didn’t reject + your selections", he: "אלבום: המלצות שלא דחיתם + הבחירות שלכם" },
  exportSelectedOnly: { en: "Only photos you explicitly selected", he: "רק תמונות שבחרתם במפורש" },
  checkExport: { en: "Check", he: "בדיקה" },
  startExport: { en: "Export {n} photos", he: "ייצוא {n} תמונות" },
  missingFiles: { en: "Missing source files", he: "קובצי מקור חסרים" },
  exportDone: { en: "Export complete", he: "הייצוא הושלם" },
  notEnoughSpace: { en: "Not enough free disk space.", he: "אין מספיק מקום פנוי בדיסק." },
  // settings
  providerTitle: { en: "AI provider", he: "ספק AI" },
  providerLocalOnly: { en: "Local analysis only", he: "ניתוח מקומי בלבד" },
  ollamaTitle: { en: "Local vision model (Ollama)", he: "מודל ראייה מקומי (Ollama)" },
  ollamaNotRunning: { en: "Ollama is not running. Install it from ollama.com and open it.", he: "Ollama לא פועל. התקינו אותו מ-ollama.com ופתחו אותו." },
  apiKey: { en: "Anthropic API key", he: "מפתח API של Anthropic" },
  apiKeyStored: { en: "Key stored ({where}). It is never sent to the browser.", he: "המפתח נשמר ({where}). הוא לעולם לא נשלח לדפדפן." },
  spendingLimit: { en: "Spending limit (USD)", he: "תקרת הוצאה (דולר)" },
  spendingLimitNote: { en: "Enforced by this app before each request (not by Anthropic’s billing system).", he: "נאכפת על ידי האפליקציה לפני כל בקשה (לא על ידי מערכת החיוב של Anthropic)." },
  estimate: { en: "Estimate", he: "הערכה" },
  runAI: { en: "Run AI analysis", he: "הרצת ניתוח AI" },
  scopeAlbum: { en: "Album photos only", he: "תמונות האלבום בלבד" },
  scopeUncategorized: { en: "Photos with uncertain moments", he: "תמונות עם רגע לא ודאי" },
  scopeAll: { en: "All photos", he: "כל התמונות" },
  confirmUpload: { en: "I confirm uploading these photos for analysis", he: "אני מאשר/ת העלאת התמונות לניתוח" },
  testConnection: { en: "Test with a synthetic image", he: "בדיקה עם תמונה סינתטית" },
  usage: { en: "Usage so far", he: "שימוש עד כה" },
  privacyControls: { en: "Delete local data", he: "מחיקת נתונים מקומיים" },
  deleteFaces: { en: "Delete all face data", he: "מחיקת כל נתוני הפנים" },
  deleteAI: { en: "Delete AI results", he: "מחיקת תוצאות AI" },
  deleteEmbeddings: { en: "Delete image embeddings", he: "מחיקת וקטורי תמונה" },
  deleteThumbs: { en: "Delete thumbnails & previews", he: "מחיקת תמונות ממוזערות" },
  deleteProject: { en: "Delete this project", he: "מחיקת הפרויקט" },
  deleteProjectNote: { en: "Removes the project database and caches. Your original photos are not touched.", he: "מוחק את מסד הנתונים והמטמון של הפרויקט. תמונות המקור לא נפגעות." },
  areYouSure: { en: "Are you sure? This cannot be undone.", he: "בטוחים? לא ניתן לבטל פעולה זו." },
  theme: { en: "Theme", he: "ערכת צבעים" },
  language: { en: "Language", he: "שפה" },
};

interface Ctx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  dir: "ltr" | "rtl";
}

const I18n = createContext<Ctx>(null as any);

function readLang(): Lang {
  try {
    const v = localStorage.getItem("wac.lang");
    if (v === "he" || v === "en") return v;
  } catch {
    /* storage unavailable */
  }
  return navigator.language?.startsWith("he") ? "he" : "en";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readLang);
  const dir = lang === "he" ? "rtl" : "ltr";
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
  }, [lang, dir]);
  const value = useMemo<Ctx>(
    () => ({
      lang,
      dir,
      setLang: (l) => {
        setLangState(l);
        try {
          localStorage.setItem("wac.lang", l);
        } catch {
          /* ignore */
        }
      },
      t: (key, vars) => {
        const entry = STRINGS[key];
        let s = entry ? entry[lang] : key;
        if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
        return s;
      },
    }),
    [lang, dir],
  );
  return <I18n.Provider value={value}>{children}</I18n.Provider>;
}

export const useI18n = () => useContext(I18n);
