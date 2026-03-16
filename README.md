
# CampusIQ
CampusIQ is a self-hosted adaptive learning platform that provides AI-driven personalization on top of human-authored content to tailor the 
learning path of each student based on their skills and comprehension level.


# Problem

Most Learning Management Platforms are opaque to the individual needs of learners. Once the course content is created it appears 
identically for all the learners irrespective of their existing skill or comprehension gaps. There is no cognitive feedback loop to identify where an individual
learner is lacking and customize their learning path based on that information. 

Beyond personalization, existing platforms also lack customization. They are built for a single domain - kindergarten, K-12, universities, or corporate training thereby
making them impossible to extend across domains. 

CampusIQ was built to solve both of these issues. 

# Key Capabilities


- **Self-hosted:** Easily deployable to your own AWS account —  mitigates data residency concerns. Your data never leaves your 
  own AWS account.
- **Extensible:** Connects to your existing content management system through a standard plugin interface. Provides S3, Google 
  Classroom, and Strapi out of the box and is extensible to anything else through the same interface.
- **Personalised Learning Paths:** A cognitive feedback loop identifies gaps in each learner's learning and adjusts their 
  path in real time to their individual needs.
- **AI Assistant:** Acts as an AI-powered assistant to augment human tutoring, grounded in your actual course content and not 
  the open internet.

# How CampusIQ Works Alongside Your Existing Tools

CampusIQ is not a replacement for your existing content management 
system (CMS) but an augmentation to deliver AI capabilities. Your 
CMS is for content creation — CampusIQ is for learning delivery.

Once deployed and configured, CampusIQ connects to your CMS. You 
do not need to sign a new SaaS contract or trust a new vendor with 
your student data — nothing ever leaves your own infrastructure. 
You keep creating content exactly the way you do today. What 
changes is that teachers get a dashboard showing which students are 
struggling with which concepts. Students get a single place to 
access all course content along with an AI tutor that adapts their 
learning path based on their progress.

# Architecture

CampusIQ is built on Amazon Web Services (AWS). It comprises 4 layers:

- **Pluggable CMS layer**
- **Multi-agent AI layer**
- **Adaptive experience layer**
- **Analytics layer**

Its pluggable CMS layer allows different institutions to plug in their existing content management system via the Content Provider Interface that transforms the incoming content into a standardized CampusIQ format before feeding into the AI pipeline. The AI layer - responsible for gap detection, tutoring, and adaptive learning path generation - comprises specialized agents orchestrated by a central orchestrator agent, all running on Amazon Bedrock AgentCore. All infrastructure for CampusIQ is defined as code using AWS CDK and deployable to your own AWS account in a single command. 

![CampusIQ Architecture](docs/architecture/campusiq-architecture.png)

# Quick Start

## Technology Stack

- **Backend Framework**: FastAPI, Python, Strands (Amazon Strands Agents SDK for agent orchestration)
- **Dependency Management**: Poetry

### Prerequisites

Before setting up the application, make sure you have the following prerequisites installed on your laptop:

- Python (version >=3.9, <4.0)
- Docker and Docker Compose

### Installation

#### Install Poetry
Install Poetry for dependency management

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

#### Clone the repository

```bash
git clone https://github.com/anshul14/campusiq.git
```

CD into the newly created repository directory
```bash
cd campusiq
```

#### Setup a Virtual Environment and Install Dependencies

```bash
poetry install
```

#### Copy and edit the campusiq.config.example.json file with your settings file
```bash
cp campusiq.config.example.json campusiq.config.json
```

#### Deploy
```bash
# Configure AWS credentials first
aws configure
# or using a named profile
export AWS_PROFILE=your-profile

# Deploy
cdk deploy
```

###  Project structure

- **src/application**: Main application code
  - **agents**: Orchestrator and specialized agents
  - **plugins/content_plugin_interface**: Individual content plugin codes for different CMS
  - **plugins/experience_plugin_interface**: Individual content plugin codes for different experiences
  - **routes**: Different API routes of the application 
  - **utils**: Utilities used in different areas in the application
- **infrastructure**: Infrastructure creation and deployment
  - **cdk**: CDK code for building and deploying the infrastructure
- .dockerignore: Files that are ignored when building the backend application docker image
- .gitignore: Files that will not be checked into Git
- poetry.lock: Python Poetry dependency management lock file
- pyproject.toml: Python Poetry dependency definition file. Poetry is only used for dependencies and not for deployment
- README.md: Well.... this file :) 


# Plugin System

CampusIQ is built on a pluggable architecture. Most institutions  have their own content management systems but without an 
intelligence layer. CampusIQ's Content Provider Interface (CPI) allows institutions to integrate their existing CMS without 
modifying it.

Once plugged in, the CPI standardises the content format required  by the downstream intelligence and personalisation layers. This 
architecture makes CampusIQ extensible — new CMS integrations  can be added by implementing the standard plugin interface.

Along with the CPI, CampusIQ also provides an experience plugin that tailors the learning experience to different domains — 
kindergarten, K-12, universities, and corporate training.

For more details see:
- [CMS Plugin Guide](docs/cms-plugin-guide/README.md)
- [Experience Plugin Guide](docs/experience-plugin-guide/README.md)

# Supported Integrations

### Content Management Systems
- Amazon S3 *(built-in)*
- Google Classroom
- Strapi
- Custom *(via CPI plugin interface)*

### Identity Providers
- Microsoft Entra ID
- Google Workspace
- SAML 2.0 compatible providers

### AWS Services
- Amazon Bedrock — Claude 3.5 Sonnet, Claude 3 Haiku
- Amazon Bedrock AgentCore
- Amazon Bedrock Knowledge Bases
- Amazon Personalize
- Amazon Transcribe

# Documentation

| Document                                                          | Description |
|-------------------------------------------------------------------|-------------|
| [Architecture](docs/architecture/ARCHITECTURE.md)                 | Full system architecture and design decisions |
| [CMS Plugin Guide](docs/cms-plugin-guide/README.md)               | How to build a custom CMS plugin against the CPI |
| [Experience Plugin Guide](docs/experience-plugin-guide/README.md) | How to configure domain-specific learning experiences |
| [IdP Setup Guide](docs/idp-setup/README.md)                       | How to connect your identity provider |
| [Domain Configuration](docs/domain-configs/README.md)             | Domain configuration reference |

# Contributing

CampusIQ is open source and contributions are welcome. Whether it 
is a new CMS plugin, an experience plugin for a new domain, a bug 
fix, or documentation improvement — all contributions are valued.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting 
a pull request.

# License

Apache 2.0 — Copyright 2026 Anshul Saxena. See [LICENSE](LICENSE) for details.