"""Explicit source-reviewed development annotations, NOT generated predictions.

No user gold was supplied. These labels were authored during implementation
and cannot measure held-out generalization. Source SHA is filled mechanically;
all expected field/heading values below are literal reviewed annotations.
"""
from pathlib import Path
import hashlib
import json
import argparse

# Header labels are database section boundaries, including explicit inline labels.
H={
'maya':[('CREATIVE SKILLS','skills'),('AWARDS & HONORS','awards'),('EDUCATION','education'),('CREATIVE PROFILE','summary'),('EXPERIENCE','experience')],
'darius':[('CONTACT','contact'),('ARCHITECTURE SKILLS','skills'),('CERTIFICATIONS','certifications'),('EXECUTIVE SUMMARY','summary'),('LEADERSHIP & ARCHITECTURE EXPERIENCE','experience'),('EDUCATION','education')],
'camila':[('MARKETING METRICS','metrics'),('GROWTH TOOLKIT','skills'),('EDUCATION','education'),('EXECUTIVE PROFILE','summary'),('PROFESSIONAL EXPERIENCE','experience')],
'julian':[('CORE COMPETENCY FRAMEWORK','skills'),('OPERATIONAL LEADERSHIP EXPERIENCE','experience'),('EDUCATION & CREDENTIALS','education')],
'claire':[('CONTACT','contact'),('SKILLS','skills'),('EDUCATION','education'),('PROFILE','summary'),('EXPERIENCE','experience')],
'devon':[('CORE COMPETENCIES & FINANCIAL SYSTEMS','skills'),('CAREER HISTORY','experience'),('EDUCATION & CERTIFICATIONS','education')],
'kavita':[('STRATEGIC SUMMARY:','summary'),('SELECT GTM LEADERSHIP & EXPERIENCE','experience'),('KEY GTM METRICS','metrics'),('SKILLS & METHODOLOGIES','skills'),('EDUCATION','education')],
'lucas':[('CONTACT','contact'),('CORE SKILLS','skills'),('CERTIFICATIONS','certifications'),('EDUCATION','education'),('PROFESSIONAL SUMMARY','summary'),('WORK EXPERIENCE','experience')],
'natalie':[('CORE COMPETENCIES & AUDIT CAPABILITIES','skills'),('PROFESSIONAL AUDIT & ACCOUNTING EXPERIENCE','experience'),('EDUCATION & CREDENTIALS','education')],
 'tariq':[('EXECUTIVE SUMMARY:','summary'),('EXECUTIVE LEADERSHIP & IMPACT','experience'),('KEY LEADERSHIP METRICS','metrics'),('TECHNICAL GOVERNANCE','skills'),('EDUCATION','education')],
'alex':[('PROFESSIONAL SUMMARY','summary'),('TECHNICAL SKILLS','skills'),('PROFESSIONAL EXPERIENCE','experience'),('EDUCATION & CERTIFICATIONS','education'),('Certifications:','certifications')],
'eleanor':[('EXECUTIVE PROFILE','summary'),('CORE EXECUTIVE COMPETENCIES','skills'),('EXECUTIVE EXPERIENCE','experience'),('EDUCATION & CREDENTIALS','education'),('Credentials:','certifications')],
'sophia':[('EDUCATION','education'),('ACADEMIC & RESEARCH APPOINTMENTS','experience'),('SELECTED PEER-REVIEWED PUBLICATIONS','publications'),('HONORS, GRANTS & FELLOWSHIPS','awards')],
'jordan':[('EDUCATION','education'),('TECHNICAL & ANALYTICAL SKILLS','skills'),('INTERNSHIP EXPERIENCE','experience'),('ACADEMIC PROJECT & LEADERSHIP','projects')],
'marcus':[('DESIGN PHILOSOPHY & SUMMARY','summary'),('TOOLKIT & METHODOLOGIES','skills'),('WORK EXPERIENCE','experience'),('EDUCATION','education')]
}
# name, email, phone, location, linkedin/github URLs
C={
'maya':('MAYA LIN-VAZQUEZ','maya.lin.design@example.com','(555) 781-9920','Los Angeles, CA',[]),
'darius':('DARIUS K. VANCE','darius.vance@example.com','(555) 304-9182','Denver, CO',['github.com/darius-cloud','linkedin.com/in/dariusvance-dummy']),
'camila':('CAMILA RESTREPO','camila.restrepo@example.com','(555) 612-4091','Miami, FL',['linkedin.com/in/camila-marketing-dummy']),
'julian':('JULIAN A. MERCER','julian.mercer@example.com','(555) 481-0294','Boston, MA',['linkedin.com/in/julianmercer-dummy']),
'claire':('CLAIRE DUPUIS','claire.dupuis@example.com','+1 (415) 555-0199','San Francisco, CA',['linkedin.com/in/claire-dummy']),
'devon':('DEVON M. HASTINGS','devon.hastings@example.com','(555) 839-2041','Chicago, IL',['linkedin.com/in/devon-hastings-dummy']),
'kavita':('KAVITA RAMANATHAN','kavita.ramanathan@example.com','(555) 234-8761','San Jose, CA',['linkedin.com/in/kavita-ramanathan-dummy']),
'lucas':('LUCAS MOREAU','lucas.moreau@example.com','(555) 492-8172','Austin, TX',['github.com/lmoreau-dummy','linkedin.com/in/lucas-m-dummy']),
'natalie':('NATALIE CHOW, CPA','natalie.chow.cpa@example.com','(555) 918-2045','New York, NY',['linkedin.com/in/nataliechow-dummy']),
 'tariq':('TARIQ AL-HASSAN','tariq.alhassan@example.com','+1 (206) 555-0184','Seattle, WA',['linkedin.com/in/tariq-ai-dummy']),
'alex':('ALEX CHEN','alex.chen.dev@example.com','(555) 019-2834','San Francisco, CA',['github.com/alexchen-dev','linkedin.com/in/alexchen-dummy']),
'eleanor':('ELEANOR R. VANCE','e.vance.executive@example.com','+1 (312) 555-8492','Chicago, IL',['linkedin.com/in/eleanor-vance-dummy']),
'sophia':('DR. SOPHIA AL-MANSOOR, PH.D.','s.almansoor.phd@example.edu','+1 (650) 555-0143','Stanford, CA 94305',[]),
'jordan':('JORDAN TAYLOR','jordan.taylor.analyst@example.com','(555) 762-9013','Seattle, WA',['linkedin.com/in/jordan-taylor-dummy']),
'marcus':('MARCUS BRODY','m.brody.design@example.com','(555) 392-7104','New York, NY',[])
}
# Per-entry title, company (location suffix excluded), date start/end, bullet count.
J={
'maya':[('Senior Brand Designer','Lumina Creative Studio','2022','Present',3),('Visual & Packaging Designer','Verve Labs','2019','2022',2)],
'darius':[('Principal Cloud Solutions Architect','StrataCore Cloud Systems','2021','Present',3),('Lead Infrastructure Architect','Apex Financial Technologies','2017','2021',2)],
'camila':[('Senior Performance Marketing Manager','Nova Health App','2022','Present',3),('Growth Marketing Lead','Solstice Commerce','2019','2022',2)],
'julian':[('Director of Business Operations','Beacon Healthcare Technologies','2021','Present',3),('Engagement Manager (Strategy & Operations)','Bain & Company','2017','2021',2)],
'claire':[('Lead Product Designer','CloudScale Networks','2022','Present',3),('Senior UX Designer','AeroMetrics Analytics','2019','2022',2)],
'devon':[('Senior FP&A Controller','Sterling Horizon Capital','2021','Present',3),('Financial Analyst','Pinnacle Advisory Partners','2018','2021',2)],
'kavita':[('Director of Product Marketing','Synthetix AI','2022','Present',2),('Senior Product Marketing Manager','Datastream Cloud','2019','2022',2)],
'lucas':[('Senior Infrastructure Engineer','Datavault Systems','2022','Present',3),('Cloud Platform Engineer','Stratosphere Networks','2020','2022',2)],
'natalie':[('Audit Controller','Vanguard Trust Partners','2021','Present',3),('Senior Accountant','Deloitte & Touche LLP','2018','2021',2)],
 'tariq':[('VP of Machine Learning Platform','Cerebro Analytics','2022','Present',3),('Director of Applied AI','Horizon Autonomous Systems','2018','2022',2)],
'alex':[('Lead Backend Software Engineer','Nexus Cloud Technologies','Mar 2023','Present',4),('Full Stack Software Engineer','Vanguard Digital Labs','Aug 2020','Feb 2023',3),('Junior Software Engineer','Apex Software Solutions','Jun 2018','Jul 2020',2)],
'eleanor':[('Vice President of Global Operations','Crestview Manufacturing & Logistics Group','2020','Present',4),('Director of Supply Chain & Manufacturing','Apex Industrial Technologies','2015','2020',3)],
'sophia':[('Postdoctoral Research Fellow','Department of Bioengineering, Stanford University','2023','Present',1)],
'jordan':[('Business Analyst Intern','Cascade Financial Services','Jun 2024','Sep 2024',3),('Operations Data Intern','Evergreen Supply Partners','Jan 2024','May 2024',2)],
'marcus':[('Lead Product Designer','Kinetix Health App','Jan 2022','Present',3),('Senior UX/UI Designer','Studio Pixel & Form','Jun 2019','Dec 2021',2)]
}
D={
'maya':['B.F.A. in Graphic Design'],
'darius':['M.S. in Computer Science','B.S. in Computer Engineering'],
'camila':['B.S. in Digital Marketing & Media'],
'julian':['Master of Business Administration','MBA','B.A. in Economics'],
'claire':['B.S. in Human-Computer Interaction'],
'devon':['B.S. in Finance & Accounting'],
'kavita':['MBA','B.S. in Economics'],
'lucas':['B.S. in Computer Science'],
'natalie':['B.S. in Accounting & Information Systems'],
 'tariq':['Ph.D. in Computer Science','B.S. in Electrical Engineering'],
'alex':['B.S. in Computer Science'],
'eleanor':['Master of Business Administration','MBA','Bachelor of Science in Industrial Engineering'],
'sophia':['Ph.D. in Computational Biology & Bioinformatics','B.S. in Molecular Biology & Computer Science'],
'jordan':['Bachelor of Arts in Information Systems & Operations Management'],
'marcus':['B.F.A. in Graphic & Interactive Media Design']
}
# Surface degree mentions are evaluated, including parenthetical MBA aliases.
# Skills are canonical dictionary mentions across ALL document text, not inferred mastery.
S={
'maya':['Figma','Adobe Illustrator','Adobe Photoshop','Adobe After Effects'],
'darius':['AWS','Azure','Kubernetes','Terraform','GitOps','ArgoCD','Apache Kafka','PostgreSQL','Snowflake','Redis','SOC2'],
'camila':['Meta Ads','TikTok Ads','Google Ads','Amplitude','Mixpanel','GA4','AppsFlyer','Adjust','Branch','Optimizely','VWO','SQL','Tableau','BigQuery'],
'julian':['Lean Six Sigma','Procurement'],
'claire':['Wireframing','Prototyping','Figma','FigJam','Journey Mapping','Usability Testing','WCAG','HTML','CSS','Agile','React'],
'devon':['Financial Modeling','SAP S/4HANA','Oracle NetSuite','GAAP','IFRS','Budgeting','Forecasting','Tableau','Power BI','SQL','Excel','VBA','Power Query'],
'kavita':['HubSpot','Salesforce','Marketo'],
'lucas':['Go','Python','C++','Kubernetes','Docker','Helm','AWS','Apache Kafka','RabbitMQ','Redis','Terraform','Linux','eBPF','GitOps','ArgoCD','OpenTelemetry','Prometheus','Grafana'],
'natalie':['SOX','GAAP','AML','Workday','Oracle NetSuite','Alteryx','SQL'],
 'tariq':['Machine Learning','Deep Learning','AWS','PyTorch','Triton','Ray','CUDA','TensorRT','vLLM','Computer Vision'],
'alex':['Go','Python','TypeScript','Java','SQL','Rust','Node.js','FastAPI','Spring Boot','PostgreSQL','Redis','Apache Kafka','GraphQL','AWS','Docker','Kubernetes','Terraform','GitHub Actions','Prometheus','React','Next.js','Tailwind CSS','Jest','Datadog','Git','Linux','Redux'],
'eleanor':['Supply Chain','Lean Six Sigma','Procurement','Risk Management','SAP S/4HANA'],
'sophia':['Deep Learning'],
'jordan':['Tableau','Power BI','Excel','Power Query','SQL','PostgreSQL','Python','Pandas','Agile','Scrum','BPMN','Jira','Confluence','Root Cause Analysis','Supply Chain'],
'marcus':['Design Systems','WCAG','Figma','Prototyping','Principle','Adobe Creative Cloud','Framer','User Research','Journey Mapping','HTML','CSS','Tailwind CSS','Git']
}
FILES={
'colorful_resume_templates_bundle':{'01_DOCX_Vibrant_Coral_Creative_Resume.docx':'maya','02_DOCX_Navy_Teal_Cloud_Architect.docx':'darius','03_PDF_Royal_Purple_Marketing_Resume.pdf':'camila','04_PDF_Emerald_Forest_Operations_Resume.pdf':'julian'},
'comprehensive_resume_test_suite':{'01_DOCX_Two_Column_Sidebar_Layout.docx':'claire','02_DOCX_Heavy_Table_Layout_Resume.docx':'devon','03_DOCX_Horizontal_Hero_Two_Blocks.docx':'kavita','04_PDF_Two_Column_Sidebar_Layout.pdf':'lucas','05_PDF_Strict_Table_Grid_Resume.pdf':'natalie','06_PDF_Horizontal_Hero_Two_Blocks.pdf':'tariq','07_DOCX_Modern_Tech_Software_Engineer.docx':'alex','08_DOCX_Executive_Corporate_Director.docx':'eleanor','09_DOCX_Academic_Research_CV.docx':'sophia','10_DOCX_Entry_Level_Business_Analyst.docx':'jordan'},
'resume_templates_test_bundle':{'01_Modern_Tech_Software_Engineer.docx':'alex','02_Executive_Corporate_Director.docx':'eleanor','03_Creative_Product_UX_Designer.docx':'marcus','04_Academic_Research_CV.docx':'sophia','05_Entry_Level_Business_Analyst.docx':'jordan'}}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('inputs',type=Path);parser.add_argument('--out',type=Path,default=Path('tests/gold'));args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    for bundle,files in FILES.items():
        for filename,persona in files.items():
            path=args.inputs/bundle/filename;name,email,phone,location,urls=C[persona]
            dates=[{'start':j[2],'end':j[3]} for j in J[persona]]
            if persona=='alex':dates.append({'start':'2014','end':'2018'})
            if persona=='lucas':dates.insert(0,{'start':'2016','end':'2020'})
            if persona=='sophia':dates=[{'start':'2018','end':'2023'},{'start':'2014','end':'2018'},{'start':'2023','end':'Present'},{'start':'2024','end':'2026'},{'start':'2020','end':'2023'}]
            gpa={'claire':'3.85','lucas':'3.88','jordan':'3.82'}.get(persona)
            record={'file':str(Path(bundle)/filename),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'persona':persona,'annotation_origin':'source-reviewed development labels authored for this task; not user gold or held out',
            'headings':[{'text':h,'canonical':c} for h,c in H[persona]],
            'fields':{'name':name,'emails':[email],'phones':[phone],'locations':[location],'urls':urls,'date_ranges':dates,'degrees':D[persona],'gpas':[{'score':gpa,'scale':'4.0'}] if gpa else [],'skills':S[persona]},
            'experience':[{'title':j[0],'company':j[1],'start':j[2],'end':j[3],'bullet_count':j[4]} for j in J[persona]]}
            (args.out/(bundle+'__'+path.stem+'.json')).write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n')
if __name__=='__main__':main()
