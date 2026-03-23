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


# 1. Overview



# 2. System Architecture
CampusIQ is a self-hosted adaptive learning platform that provides AI-driven personalization on top of human- authored
content to tailor the learning path of each student based on their skills and comprehension level. 

It is architected as a pluggable framework that can be plugged-in to your existing content management system (CMS)
and act as an AI layer of it. 

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
