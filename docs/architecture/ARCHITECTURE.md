# CampusIQ Architecture

## Table of Contents

1. [Overview](#1-Overview)
2. [System Architecture](#2-System-Architecture)
3. [The Cognitive Learning Loop](#3-the-cognitive-learning-loop)
4. [Content Provider Interface](#4-content-provider-interface)
5. [Multi-Agent Design](#5-multi-agent-design)
6. [Authentication Architecture](#6-authentication-architecture)
7. [Data Architecture](#7-data-architecture)
8. [Technology Decisions](#8-technology-decisions)
9. [Deployment Model](#9-deployment-model)
10. [Extensibility](#10-extensibility)


## 1. Overview

CampusIQ is an AI powered adaptive learning platform that augments the learning delivery capabilities of institutions. 
Most of the learning management platforms that exist today are static in nature. They provide the same learning path to each 
student oblivious to the gaps in learning of each student. This leaves a very big gap in a student's ability to excel, since continued learning is built on top of what you already know
and if the previous concepts are weak it affects the future learning. 

CampusIQ is built on three core architectural principles. First, it is self-hosted. You deploy it to your own AWS account and hence none of your
student data ever leaves your infrastructure. Second, it is pluggable to your existing content management system (CMS). You continue to create content
as you do today, and CampusIQ works on top of that content seamlessly. No hassle to move content neither to learn any new CMS. CampusIQ has 
native integrations with Google Classroom, Strapi API, and S3 and can easily be integrated with any other CMS you use by implementing the plugin interface.
Third, it is AI-native — artificial intelligence is not bolted on top of the platform as an afterthought. It is the core delivery mechanism. 
The Cognitive Learning Loop, the AI Tutor, and the gap detection system are not optional add-ons — they are the platform.

These three features makes CampusIQ unique from the existing LMS. Self-hosted AI native learning platforms do not exist today. You either have to 
subscribe to a SaaS platform, which means your student data lives on someone else's servers, or you build a custom solution on top to provide AI capabilities, which is hard and time-consuming. 


## 2. System Architecture

CampusIQ is organised into four layers that work together as a
closed feedback loop. Each layer has a distinct responsibility but
no layer operates independently — content flows into intelligence,
intelligence drives delivery, and delivery generates data that
feeds back into intelligence.

![CampusIQ Architecture](campusiq-architecture.png)

### 2.1 Content Sources Layer

CampusIQ has a plugin architecture that allows you to bring your
own CMS — Google Classroom, Strapi, or S3. It also has a built-in
content creation layer for institutions that do not have an existing
CMS. The Content Plugin Interface (CPI) normalises content into a
standard format that the CampusIQ backend understands. Content is
ingested into an S3 bucket in your own AWS account — this ensures
the AI layer is not dependent on the CMS being available and
eliminates latency from live API calls during a student session.
The ingested content forms the Knowledge Base for Amazon Bedrock
on which the language models ground their answers. The AI layer
never talks to the CMS directly — only to the CPI.

### 2.2 AI Intelligence Layer

The AI intelligence layer comprises Orchestrator and Tutor Agent that runs in Amazon Bedrock AgentCore.
The Orchestrator enriches the context with the student's gap summary before sending it to Tutor Agent. The Tutor
Agent gets this enriched context and uses it to answer any questions - tie up with the previous concepts
that the student has gap in. The tutor agent always grounds its answers in the actual content which forms the basis
for Amazon Bedrock Knowledge Base. The AI intelligence layer also has four Lambdas - Gap Detection - responsible for translating the quiz performance into a concept-level
weakness model for the student , Recommendation - responsible for taking the gap signal and translating it into a concrete learning path, 
Content Adaptation, Assessment

### 2.3 Adaptive Delivery Layer

The adaptive delivery layer is the mechanism through which the Cognitive Learning Loop's output reaches the student. A student's  learning path is personalized based on the gap
profile. Amazon Personalize ingests this gap profile and interaction history and produces the personalized learning path for the student. 
The interaction between components is asynchronous and event-driven, orchestrated by Amazon EventBridge. The personalized learning path is stored in 
DynamoDB and read by CourseShell - the navigation container that presents the personalized module sequences to the student. The whole process is automated without any teacher intervention. The learning path record has a 24-hour TTL that ensures
that the CourseShell is always displaying the recent state and not a stale snapshot.

### 2.4 Analytics Layer

The analytics layer is responsible for translating the student's interaction data into actionable insights for the teachers and administrators. 
DynamoDB streams feed the analytics pipeline -  data flows from DynamoDB Streams through a Lambda processor into an S3 analytics lake,
where AWS Glue crawls and catalogues it, Athena queries it, and QuickSight renders it as a faculty dashboard. The dashboard comprises four panels: class health showing average mastery scores
and at-risk student counts, a concept gap heatmap showing which concepts the cohort is collectively struggling with, a student progress timeline showing individual 
mastery trajectories over time, and a content effectiveness scoreboard ranking modules by the quiz score improvements they produce.
0.7 is defined as the gap_severity threshold and a gap_severity value > 0.7 triggers an SNS alert to the teacher. The analytics layer never queries the operational DynamoDB table  
freeing it for low-latency student interaction. All the analytics reads go through the S3 lake via Athena.

### 2.5 How the Layers Connect

The content from the content management system flows through the content plugin interface, which standardizes the content to CampusIQ standard format and pushes to an S3
bucket, which is used as the data source for Bedrock Knowledge Base. Whenever a student submits a quiz, the quiz
results are calculated and recorded in DynamoDB from where they are streamed via EventBridge to the Gap Detection lambda
that calculates the gap_severity and writes to the DynamoDB. If the gap_severity threshold value (>= 0.7) is breached the EventBridge event
is triggered and the Recommendation Lambda calls Amazon Personalize and Personalize updates the learning path. 
Next time the student logs into CampusIQ and opens CourseShell they are presented the updated LearningPath. 
Whenever a student asks a question to the Tutor Agent, the Orchestrator injects gap context and the tutor grounds its answer in Bedrock Knowledge Base. 
All interactions are routed through the DynamoDB streams to the analytics pipeline which feeds the Faculty Dashboard. 

No layer in the whole system operates in isolation. Every student interaction generates a signal that propagates through the system and eventually reshapes
the student's experience.


## 3. The Cognitive Learning Loop

Cognitive learning focuses on internal mental processes in learning. Learning is not passive - it requires
learners to actively process information, and that processing happens at a different rate and depth for each individual. 
Most of the learning management systems that exist today have a static learning framework and are oblivious to this reality. 
A student who struggles with Newton's laws of motion in Week 3 receives the same Week 4 content
as a student who has mastered the concept. The platform is unaware of this gap and has no mechanism to identify and respond to it - every student
continues on the same path regardless of whether they understood the previous concept or not.  

CampusIQ overcomes this limitation through what we call the "Cognitive Learning Loop" - a closed-feedback system that  triggers on every quiz submission, 
where specialized components process that signal and adjust the student's learning path in real-time. 

![Cognitive Loop Architecture](cognitive-loop-architecture.png)
### 3.1 The Entry Point — Quiz Submission

Quiz submission is the single entry point to the Cognitive Learning Loop, everything else in the system is triggered by this event.  
This is deliberate since quiz performance is the most reliable signal of genuine comprehension. Other indicators and metrics
such as time on page or video play percentage are easy to fabricate. 

When a student submits a quiz the following sequence occurs:

1. The frontend calls POST /api/v1/courses/{courseId}/modules/{moduleId}/quiz/submit
2. The Submit Lambda scores the quiz by comparing answers against correct_ids and calculates score_pct
3. The Lambda builds the concept_scores map — mapping each concept to a score between 0.0 and 1.0 based on the questions tagged with that concept
4. The QuizResult record is written to DynamoDB with the concept_scores map stored on it

The concept_scores map is the signal that drives the entire loop. Without concept_scores the system has no way of
translating a quiz result into concept identifiers. The platform knows that a student scored 65% on the quiz but has no
way of knowing which concepts are weak and which are strong. 
**Concept Score Map**

Example concept_scores on a Physics Week 3 quiz result. In this example the student scored well on inertia but struggled with friction, acceleration, and Newton's Third Law.
```json
    
          {
              "friction":      0.4,   
              "inertia":       0.9,   
              "acceleration":  0.7,   
              "newtons_third": 0.5  
          }
```

The `concept_scores` map becomes possible because of concept tagging.
Without it the system has no way to identify which concepts are weak.
The `concept` field on each question is what enables this mapping —
the Assessment Lambda sets it when generating the quiz draft and the
teacher can edit it when reviewing.
```json
              {
                  "id":      "q1",
                  "type":    "SINGLE",
                  "text":    "Which of Newton's laws describes inertia?",
                  "concept": "inertia",    
                  "correct_ids": ["a"]
              }
```
### 3.2 Gap Detection

Once the quiz results are written to the DynamoDB, the stream processor lambda fires QuizCompleted event. This event has an EventBridge
rule on it that routes the events to the Gap Detection Lambda. This lambda is responsible for translating the quiz performance into a concept-level
weakness model for the student. 

Following sequence of steps occur inside it:
1. Read concept_scores map from the event. 
2. Look up existing gap records for each concept.
3. Calculate new gap_severity.
4. Write updated gap record to DynamoDB.

The gap_severity scoring model calculates the gap in a student's understanding of the concepts. It is the inverse of the concept mastery and is 
calculated on a scale of 0.0 to 1.0 with 0.0 means complete mastery and 1.0 means completely unknown. 0.7 is defined as the risk-threshold.

| gap_severity | 	Meaning                                                               | 	Action                                                                                       |
|--------------|------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| 0.0 – 0.3    | 	Strong — student has demonstrated consistent mastery of this concept	 | No action. Path does not prioritise this concept.                                             |
| 0.3 – 0.6    | 	Developing — student partially understands but has some gaps	         | Noted. Tutor Agent aware but no path change triggered.                                        |
| 0.6 – 0.7	   | Weak — student is consistently struggling with this concept	           | Noted. Included in Orchestrator context enrichment. Path may adjust.                          |
| 0.7 – 1.0    | 	At-risk threshold exceeded — student has a significant knowledge gap	 | GapDetected EventBridge event fires. Recommendation Lambda triggered. Faculty alert may fire. |

While calculating gap_severity, recent attempts are weighted more than older ones so that the system reflects current state not historical average. 
As an example, if a student scored [0.4, 0.3, 0.5] in friction across 3 quizzes the weighted average is approximately 0.41 and the gap_severity = 1.0 - 0.41 = 0.59

The gap_severity is written to the DynamoDB stream and the Stream Processor Lambda checks the new gap_severity. If it exceeds 0.7, a second
EventBridge event fires - GapDetected and the loop continues. If the gap_severity is below 0.7, the loop stops for this cycle. 

0.7 is the loop's gating threshold to prevent the Recommendation Lambda from running after every quiz submission - which would
be wasteful and disruptive. It is invoked only when the student has demonstrated genuine weakness in a concept. This threshold is configurable in the
domain config file. 

### 3.3 - Learning Path Adaptation

Based on the gap_severity value (>0.7) the Recommendation Lambda is triggered. This lambda is responsible for taking the gap signal and translating it into a concrete learning path - an ordered list of
modules the student should work through next. 

Following sequence of steps occur inside it:
1. Read student's full gap profile from DynamoDB.
2. Call Amazon Personalize get_recommendations endpoint with student ID and gap context as item metadata.
3. Map Personalize recommendations to module IDs
4. Write updated LearningPath to DynamoDB.

The Recommendation Lambda reads the student's gap profile by querying GSI2 - PK = STUDENT#{sub}, ScanIndexForward=False and get all the gaps sorted by severity descending as response. Top 5 weakest
concepts are returned. Once the gap context is returned, the Lambda calls Amazon Personalize and pass it student ID and gap context as metadata. Personalize then returns ranked content recommendations based on student's interaction
history and gap profile.

*Personalize requires interaction history to make good recommendations but when CampusIQ is first deployed for an institution it does not have any interaction history. This is called the cold start problem.
Since it does not have any interaction history, Personalize during cold start falls back to popularity-based recommendations - it recommends modules that most students at that difficulty level engage with. So 
it is not personalized, but not completely random either. As students use the platform and interaction events accumulate, Personalize learns patterns, and it updates its model automatically as new interactions arrive - no manual retraining is needed.*

Once the LearningPath is returned it is then updated in DynamoDB.

```json
{
    "PK":                   "STUDENT#cognito-sub-abc",
    "SK":                   "PATH#phys101",
    "course_id":            "phys101",
    "recommended_modules":  [
        "week3-friction-remediation",   
        "week3-newtons-laws",           
        "week4-forces",                
        "week2-dynamics-review"   
    ],
    "current_module_id":    "week3-friction-remediation",
    "rationale":            "Prioritising friction remediation — gap severity 0.8. Newton's Third Law also flagged.",
    "generated_at":         "2026-03-15T14:23:00Z",
    "expires_at":           "2026-03-16T14:23:00Z",
    "ttl":                  1773936180
}

```
The LearningPath has a 24-hour TTL. This is done intentionally to ensure that the path is always based on the student's most
recent state and not a week-old snapshot. If when the student loads their course and the path is not found, the learning-path endpoint
triggers a fresh Personalize recommendation synchronously before responding. 

When a student logs into the platform and open CourseShell, the learning path endpoint is called. The fresh LearningPath record is read, which
reflects the gap detection and the student is guided toward remediation content without any manual teacher intervention. 

GET /api/v1/students/me/courses/phys101/learning-path
Response
```json

{
    "course_id": "phys101",
    "recommended_modules": [
        {
            "module_id": "week3-friction-remediation",
            "title":     "Understanding Friction — A Closer Look",
            "rationale": "Recommended based on recent quiz performance"
        },
        {
            "module_id": "week3-newtons-laws",
            "title":     "Newton's Laws of Motion",
            "rationale": "Re-attempt after remediation"
        }
    ],
    "current_module_id": "week3-friction-remediation",
    "generated_at":      "2026-03-15T14:23:00Z",
    "expires_at":        "2026-03-16T14:23:00Z"
}

```
###  3.4 — Tutor Context Enrichment

Every time a student asks the AI Tutor a question, the Orchestrator is called. One of the orchestrator
agent jobs is context enrichment - it injects the student's current gap summary into the prompt before dispatching
it to the Tutor Agent. 

For building the gap summary, the Orchestrator reads the student's top gaps from DynamoDB via GSI2. It then
injects this gap summary into the Tutor Agent's system prompt alongside student's active learning path and domain config. 

Enriched Context 
```json
{
    "student_profile": {
        "name":   "John Smith",
        "domain": "university",
        "grade":  "sophomore"
    },
    "gap_summary": [
        {"concept": "friction",      "severity": 0.8, "label": "needs-attention"},
        {"concept": "newtons_third", "severity": 0.5, "label": "developing"},
    ],
    "active_learning_path": {
        "current_module": "week3-friction-remediation",
        "next_module":    "week3-newtons-laws"
    },
    "domain_config": {
        "tutor_persona": "You are a university-level physics tutor...",
        "temperature":   0.7
    }
}

```
The Tutor Agent's system prompt includes the gap context explicitly.
For example — if a student has a friction gap of 0.8, the prompt
instructs the Tutor to proactively connect answers about Newton's
Laws to friction concepts, even if the student did not ask about
friction directly.

Without the gap context, the Tutor Agent is reactive and only answers the question that the student asks. With gap context, the
Tutor Agent becomes proactive since it now has the context about the gap and ties its response to the weak area. The student 
receives targeted help even when they do not know to ask for it. 

## 4. Content Provider Interface

Content Provider Interface (CPI) separates the institution's content management system from the CampusIQ platform. The CPI layer acts as a boundary beyond which the platform
doesn't need to know anything about the CMS. The institutions integrate their CMS with CampusIQ by implementing the CPI - a standard contract that transforms CMS specific content
into a format CampusIQ understands. This is what distinguishes CampusIQ as a framework rather than a platform - the AI layer works without any CMS modification. 

### 4.1 The Standard Contract

The CPI defines five actions that every plugin must implement - fetch_content fetches a single content item from the CMS by course and module ID, 
search_content searches for content items matching a query string, list_courses lists all available courses from the CMS, 
get_metadata returns metadata for a specific content item, ingest_content triggers the ingestion of content into the CampusIQ knowledge base pipeline. 

Every plugin must return a CPIContent object - the standard output that the CampusIQ platform consumes. CPIContent object carries
the content_id, title, content_type, and metadata including domain, difficulty, and the source CMS. The content itself is carried in three
optional fields depending on the type of content - body carries Markdown text for rich text content, content_url carries the S3 object keys
for PDFs, and video_url and transcript_url carry the HLS stream URL and WebVTT path respectively for video content. It is a deliberate
decision to only populate the relevant field to make the contract explicit about what type of content each response carries and prevents the platform
from having to guess. So as an example, a PDF response sets content_url and leaves body and video_url empty. 

### 4.2 Built-in Plugins

Out of the box CampusIQ provides three built-in plugins. The S3 plugin is the default and is the correct choice for institutes that create the content directly in CampusIQ. 
S3 plugin requires no external CMS - the content is read from the institution's own S3 bucket and is stored in a convention-based folder structure following the pattern
{domain}/{courseId}/modules/{moduleId}/content.md. The Google Classroom plugin connects via the Classroom API v1 and Drive API v3 for fetching coursework and attachments. Google 
Cloud Pub/Sub webhooks are configured to receive real-time notifications when a new course is published. To maintain continuity, the plugin re-registers with Pub/Sub every five days because the registrations
expire after every seven days. The Strapi plugin connects via the Strapi REST API v4. Since different Strapi installations use different field names for the same content, field names are made configurable 
via campusiq.config.json rather than hardcoded. A template plugin also ships in the repository at src/application/plugins/content_plugin_interface/template as a starting point for building integrations
with any other CMS. 

### 4.3 Content Ingestion Pipeline

Once the CPIContent object is returned by the plugin, the ingestion Lambda takes over, and it routes based on content_type. 
Markdown content is saved as .md, PDF content is saved as .pdf to the institution's own S3 bucket in the convention-based folder structure. The video content 
after saving to S3 triggers two parallel events - MediaConvert transcodes the video to HLS for adaptive streaming and Transcribe generates a WebVTT transcript. 
Also, every S3 write automatically triggers Bedrock Knowledge Base sync to ingest the new content and make available to the Tutor Agent. 
As content moves through the pipeline an ingestion manifest is written to DynamoDB tracking the status from pending to processing to complete. The teachers can check this status via the API to know 
when the new content is available to students. An important architectural decision is to make the ingestion pipeline opaque to the internally created or externally uploaded content. The same ingestion pipeline 
is triggered and performs the same steps whether CampusIQ is used for content creation or any other CMS. The AI layer makes no distinction. This is what the Unified Ingestion Pipeline pattern means in practice. 

### 4.4 Adding a Custom Plugin

Adding a new CMS plugin requires no changes to the CampusIQ platform. The plugin class must extend the ContentPluginInterface and implement its five abstract methods - fetch_content, search_content, 
list_courses, get_metadata, and ingest_content - and register the plugin type in campusiq.config.json. In case, the new CMS uses non-standard field names, add a field_mapping section to the config file mapping
non-standard to the standard field names, and the platform will read from it at runtime. The template plugin at src/application/plugins/content_plugin_interface/template is the recommended starting point - it 
includes the class skeleton, method signatures, and inline documentation. See docs/cms-plugin-guide/ for the full implementation. 

## 5. Multi-Agent Design

CampusIQ is architected on single responsibility principle and hence has multiple modular and specialized components rather than one monolithic agent.
There are two runtimes - Amazon Bedrock AgentCore and AWS Lambda. The architecture follows a hub-and-spoke pattern where the hub - the Orchestrator intercepts the 
request first - enriches it with student's gap summary, active learning path, student profile, and domain config before dispatching to the Tutor Agent.  
This leaves the Tutor Agent - a spoke, with a single responsibility of answering questions grounded in the content. It does not have to worry about routing, context enrichment, or what other
components are doing. In the absence of this pattern each component will have to manage the routing of other components making it hard to maintain. With Hub and Spoke each spoke agent is simple with
a single responsibility and all the complexity lives in the Orchestrator. Adding a new spoke agent would mean adding one new component without changing any existing agent. At any point the Orchestrator
has the full picture. 
 
In CampusIQ only the Orchestrator and Tutor Agent are in Amazon Bedrock AgentCore.The other four components are Lambda functions triggered by 
EventBridge — they are not spokes in the AgentCore sense, they are separate event-driven processors. So the Hub and Spoke pattern applies specifically to the AgentCore layer.

### 5.2 Lambda-Based Components

When a student submits the Quiz, the Submit Lambda is triggered. It scores the quiz, builds concept_scores, 
and writes quiz results to DynamoDB. The DynamoDB stream fires a quiz completed event that triggers
the Gap Detection lambda. The Gap Detection lambda reads concept_scores from the event, looks up
existing gap records from the DynamoDB for that student and calculates the gap_severity using weighted average of historical scores. It then
updates the KnowledgeGap record to DynamoDB.

The update triggers another event and if the gap_severity > 0.7, the recommendation lambda is triggered.
It reads the student's gap profile from DynamoDB via GSI2, calls Amazon Personalize get_recommendations
with gap context, and writes updated LearningPath record to DynamoDB with 24hr TTL. 

The Assessment Lambda is triggered via HTTP POST /quiz/generate request when a teacher 
clicks "Generate Quiz Draft" in the quiz editor. It receives the module content and then calls
Bedrock InvokeModel and returns structured JSON quiz draft with concept tags on them. The teacher
reviews, edits, and publishes the draft to make it available to students. 

When a students gap_severity exceeds 0.85 the Content Adaptation Lambda rewrites the module Markdown
content at a lower difficulty level. This only works on Markdown - PDF and video cannot be adapted. 
The adapted variant is saved in S3 alongside the original.

The Assessment Lambda and Content Adaptation Lambda are not part of the cognitive learning loop.
The Assessment Lambda is part of teacher-facing flow and Adaptation lambda is an optional feature. 

None of these components require specialized features such as conversational memory, RAG integration,
or streaming token responses. They receive a single input, perform a specific task, and produce
a single output. Lambda with direct Bedrock InvokeModel calls is simpler, cheaper,
and faster for these event-driven processing tasks than running
them in AgentCore.

### 5.3 Model Selection

CampusIQ makes use of different models for different tasks. 
Claude 3.5 Sonnet is used for Orchestrator - that requires multi-step reasoning and context enrichment to make judgements, 
Tutor Agent that needs conversational depth and nuanced educational explanations and Gap Detection Lambda that has to analyze concept scores.
Claude 3 Haiku is used for Assessment Lambda that has simpler task of returning JSON output quickly and Content Adaptation Lambda that does rewriting of module - a comparatively
lower complexity task. 
Model selection is configurable per domain in the domain_config
file — K-12 uses stricter settings and simpler models, university
deployments use Sonnet with higher temperature for richer
explanations, and corporate deployments use lower temperature for
precise factual responses. The principle behind model selection
is to match model capability to task complexity rather than cost.

## 6. Authentication Architecture

Most institutions already have their own Identity systems to authenticates the users. CampusIQ connects to the same IdP rather than replacing it.
None of the users have to re-create a separate account for CampusIQ and can continue using the underlying IdP. This removes the single biggest adoption barrier. 

### 6.1 The Login Flow

When a user lands on CampusIQ login page and enters their institutional email, CampusIQ reads the domain and redirects the user to their institution's own IdP 
login page (Microsoft, Google, or SAML provider). The users authenticate with their familiar IdP system with the existing username and password. 
Once authenticated, users are redirected back to CampusIQ with an authorization code. CampusIQ exchanges the authorization code for tokens server side. 
On successful login, the user lands on CampusIQ dashboard. Everything is transparent to the user — CampusIQ never sees the
student's password and the whole process takes about 10 seconds.

### 6.2 Cognito as the Federation Broker

Amazon Cognito sits between IdPs and the application. Without Cognito the application will have to handle three different protocols (Entra OIDC, Google OIDC, SAML 2.0)
with three different token formats and three different validation mechanisms. Cognito makes all this handling trivial since it speaks all three protocols. It issues one consistent JWT 
to the application regardless of the underlying IdP. The CampusIQ application only interacts with Cognito and does not have to care about the IdP. Cognito also handle claim 
normalization. For example, Microsoft calls the user ID 'upn', Google calls it 'email', SAML calls it whatever — Cognito maps all of these to consistent attributes that the application understands.
There is also a pre-token Lambda that fires before every token issuance. Its job is to enrich the JWT with CampusIQ-specific claims: institutionId, studentId, grade, idpProvider. 
The Cognito sub then becomes the stable DynamoDB identifier — PK = STUDENT#{sub} surviving any future IdP changes.

### 6.3 Supported Identity Providers

CampusIQ supports three identity provider patterns out of the box. 
Microsoft Entra ID uses OIDC protocol. The institution registers CampusIQ as an enterprise application in their Entra tenant and provides the tenantId and client credentials.
Google Workspace also uses OIDC protocol - as a safety measure the hd parameter restricts login to the institution's domain only, blocking personal Gmail accounts from 
accessing the platform, which is critical for K-12 deployments. SAML 2.0 covers
any other institutional IdP — Okta, Shibboleth, PingFederate, and
ADFS are all supported. To establish trust relationship between the institution's IdP and CampusIQ the institution's IT team needs to import the CampusIQ SP metadata XML into 
their IdP. Setup guides for each provider ship in the repository
at docs/idp-setup/. Authentication is pluggable in the same way the CMS is - the institution brings their identity system
and CampusIQ connects to it without requiring a new user directory.

### 6.4 Role-Based Access Control

CampusIQ uses two-layer role-based access control (RBAC). Cognito groups carry the coarse role in the JWT and the Lambda Authorizer at API Gateway 
applies fine-grained resource-level policies on every API call. CampusIQ has five roles


| Role                 | 	Description                                                                        | 	
|----------------------|-------------------------------------------------------------------------------------|
| Student              | 	Learners — view content, take quizzes, use AI Tutor, track own progress	           |
| Teacher / Instructor | 	Course owners — upload content, view faculty dashboard, review quiz analytics      |
| Admin	               | Deployment administrators — manage courses, users, plugin config, platform settings |
| Parent / Guardian    | 	K-12 only — read-only view of their linked child's progress summary                |
| Ops                  | 	Platform operator — the person or team who deployed and manages CampusIQ           |

The Lambda Authorizer goes beyond Cognito's built-in authorizer —
it enforces resource-level policies on every request. A student
can only access their own quiz results, a teacher can only write
to their assigned courses, and a parent can only read their linked
child's progress data.

## 7. Data Architecture

CampusIQ uses two different data stores. DynamoDB for operational data and S3 for content. They serve different needs. 

### 7.1 Single-Table Design

CampusIQ uses a single DynamoDB table per deployment for all operational data. 
All entities — courses, modules, students, enrolments, progress, quiz results, gaps, learning paths — live in one table partitioned by composite keys. DynamoDB cannot
join tables efficiently and hence everything related is co-located under the same partition key.
This is the DynamoDB best practice for serverless applications: it minimises hot partitions, eliminates cross-table transactions, 
and enables efficient composite queries via GSIs. For example, a course record has PK = COURSE#phys101 and
SK = METADATA, a student profile has PK = STUDENT#abc and
SK = PROFILE, and a progress record has PK = STUDENT#abc and
SK = PROGRESS#phys101#week3 — all in the same table, distinguished
only by their key values.

DynamoDB's on-demand billing model also makes it the right choice
for self-hosted deployments — it scales to zero when idle, meaning
small institutions with 200 students pay nothing outside active
usage hours.

CampusIQ uses three Global Secondary Indexes on the main table, each serving a different purpose and built for a specific query category. 
GSI1 enables course-scoped queries for teachers and administrators. It flips the query axis so that querying GSI1 with PK = COURSE#{courseId}
returns all students enrolled in a course, all quiz results, and
all progress records without scanning every student record
individually. 
GSI2 enables the Orchestrator to retrieve a
student's weakest concepts in a single query — it uses
PK = STUDENT#{sub} with a zero-padded severity string as the
sort key, so querying with ScanIndexForward=False returns the
highest severity gaps first. GSI3 enables at-risk detection for
the faculty alert system — it uses PK = COURSE#{courseId} with
the same severity sort key, so querying with SK >= 0.700 returns
all students in a course whose gap severity has crossed the
at-risk threshold in one efficient query.

### 7.2 Content Storage

All content for an institution is written in its own S3 bucket in a convention-based folder structure {domain}/{courseId}/modules/{moduleId}/content.md.
All three content types are stored differently - markdown as content.md,PDFs as .pdf, and video as HLS segment plus transcript.vtt. To prevent accidental deletions and 
maintain history, S3 versioning is enabled retaining the latest 10 versions per object. To reduce latency, Amazon CloudFront serves static content to students. S3 also serves 
as the knowledge store for Amazon Bedrock Knowledge Bases. 

### 7.3 — DynamoDB Streams and the Analytics Pipeline

The operational data and analytics data are kept separate so as
not to overburden a single data source. DynamoDB Streams feed
two separate pipelines — a stream processor fires EventBridge
events to trigger the Cognitive Learning Loop, and a second
stream processor writes data to an S3 analytics lake where it
flows through Glue and Athena into QuickSight. The operational
DynamoDB table is never queried for analytics, keeping it free
for low-latency student interactions without degrading performance.

## 8. Technology Decisions

Every technology choice in CampusIQ was made deliberately. This section documents the reasoning behind each major decision.

### 8.1 Python over TypeScript for Backend

Python is the primary backend language for backend and CDK code. Boto3 is mature, well-documented, 
and first class in Lambda. Having a good understanding and familiarity with Python reduces cognitive load during development. It also reduces the adoption curve for the
platform as Python has a broad base in the developer community. Typescript is used for the frontend — Next.js and React components. There is a clear split between the languages - no 
language confusion between layers. 

### 8.2 DynamoDB over Relational Database

CampusIQ has predictable key-value lookups and not complex joins, so a NoSql database makes sense. Also, DynamoDB is serverless and scales to zero when not in use, which is
a huge cost benefits for small institutions. Adding a new attribute to any entity is a write operation and not an ALTER TABLE like in a relational database. 
Native DynamoDB streams integration powers the Cognitive Loop and Analytics pipeline. No middleware logic is required to trigger them. Also, analytics queries goes to Athena 
not DynamoDB — so the lack of SQL on the operational DB is not a limitation.

### 8.3 Amazon Bedrock AgentCore over Custom Orchestration

Building a custom production grade orchestration layer is technically complex and operationally expensive. AgentCore is a production grade runtime service
that provides different features such as Agent Runtime, built-in session support, and native knowledge base integration which makes it an obvious choice for the platform. 
With AgentCore there is no operational overhead of maintaining infrastructure. AgentCore does add latency versus a custom solution but the operational simplicity outweighs that
for a self-hosted open source framework. 

### 8.4 FastAPI over Flask or Django

FastAPI shines in performance being significantly faster than Flask for async workloads. It has an excellent Async support which is important for streaming Bedrock responses. 
FastAPI also has native integration with Pydantic for request validation and OpenAPI docs are generated automatically. CampusIQ does not need an ORM, admin panel, or template
engine - hence Django was ruled out. 

### 8.5 REST over GraphQL

REST has a broad adoption and is widely understood by the open source contributors which made it a viable choice. API Gateway has native REST support with built-in
Lambda Authorizer integration. CampusIQ's access patterns are well-defined and bounded and hence GraphQL was not needed whose main advantage lies in its flexible querying. 
Multi-entity page loads are solved with composite GET endpoints e.g. GET /courses/{courseId}/dashboard returns everything the faculty dashboard needs in one call.
GraphQL would have added complexity in the framework that would have deterred open source contributors.

### 8.6 AWS CDK over Terraform or CloudFormation

CDK has Python support that matches the backend language and helps in making one language throughout the infrastructure layer. CDK also provides higher-level abstractions
than CloudFormation and is less verbose and more readable. CampusIQ also ships CDK constructs that institutions can customise. Choosing Terraform would have required learning
HCL - an additional language for contributors. CloudFormation YAML is too verbose for complex infrastructure — CDK's higher-level abstractions produce significantly more readable and maintainable code.



