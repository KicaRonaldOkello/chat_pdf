import { Component, inject } from '@angular/core';
import { ActivatedRoute, RouterLink, RouterLinkActive } from '@angular/router';

interface LegalSection {
  heading: string;
  paragraphs: string[];
}

interface LegalDoc {
  title: string;
  updated: string;
  intro: string[];
  sections: LegalSection[];
}

const PRIVACY_DOC: LegalDoc = {
  title: 'Privacy Policy',
  updated: 'Last updated and effective date: 19 August 2026',
  intro: [
    `Our commitment to privacy and data protection is reflected in this Privacy Policy, which describes how we
    collect and process "personal information" that identifies you, like your name or email address. Any other
    information is "non-personal information." If we store personal information together with non-personal
    information, we treat the combination as personal information.`,
    `References to our "Service" in this Policy include our website, applications, and other products and services.
    This Policy applies to our Service. Third-party services that we integrate with are governed by their own
    privacy policies.`,
  ],
  sections: [
    {
      heading: 'Information Gathering',
      paragraphs: [
        `We learn information about you in a few ways: (a) you directly provide it to us; (b) we collect it
        automatically through our products and services; and (c) third parties tell us information about you.`,
        `Information you provide directly. We collect your name, email address, and profile picture when you sign in
        with your Google account, and we create a unique user ID for you. We collect and retain the documents and
        other files you upload, your prompts and chat history, and the summaries, answers, and other output generated
        for you in connection with delivering the Service. If you make a purchase, payment details are collected and
        processed by our payment processor; we do not store your full card details.`,
        `Information collected automatically. When you use the Service, our systems log your Internet Protocol (IP)
        address and information about your device, including device type, operating system, browser, and other
        software. We collect general location information derived from your IP address, and we log your activity on
        the Service, including pages viewed, features used, queries submitted, token usage, file names, access times,
        and other details about your use of the Service.`,
        `Information from third parties. We receive information from third-party sources, including Google when you
        sign in, and from service providers that perform functions on our behalf, such as hosting, storage,
        analytics, and AI model providers.`,
      ],
    },
    {
      heading: 'Sensitive Information',
      paragraphs: [
        `The Service is not designed or intended to collect or process sensitive personal information, such as health
        information, financial information, or biometric information. Do not upload documents containing such
        information unless you are legally permitted to do so.`,
      ],
    },
    {
      heading: 'Information Use',
      paragraphs: [
        `We use personal information about you to: (a) provide you with our Service, including processing and
        indexing your documents and generating answers, summaries, citations, and audio; (b) improve and develop our
        Service; (c) communicate with you, including about your account and changes to our terms or policies; (d)
        provide customer support; and (e) protect the security and integrity of the Service, prevent fraud and
        abuse, and comply with legal obligations.`,
        `We do not train models on your documents, and we do not sell your personal information.`,
      ],
    },
    {
      heading: 'Information Sharing',
      paragraphs: [
        `We share information about you: (a) when we have asked for and received your consent; (b) as needed with
        third-party service providers — including hosting, storage, and AI model providers — to process or provide
        the Service to you, only where those providers agree to provide at least the same level of privacy protection
        we are committed to under this Policy and, for AI providers, to refrain from training on your content; (c) to
        comply with laws or respond to lawful requests and legal process, provided that we will notify you unless we
        are legally prohibited from doing so; (d) where we reasonably believe it is necessary to prevent harm to the
        rights, property, or safety of you or others; and (e) in the event of a corporate restructuring, merger,
        acquisition, or change in our organizational status to a successor or affiliate.`,
        `Some of our Services include integrations, references, or links to services provided by third parties whose
        privacy practices differ from ours, including Google for sign-in. If you provide personal information to any
        of those third parties, or allow us to share personal information with them, that data is governed by their
        privacy statements. Finally, we may share non-personal information in accordance with applicable law.`,
      ],
    },
    {
      heading: 'Google Sign-In Data',
      paragraphs: [
        `Our use of information received from Google APIs adheres to the Google API Services User Data Policy,
        including the Limited Use requirements. We use this information only to provide the sign-in feature you
        invoke. We do not use it, whether raw, aggregated, or derived, to develop, train, or improve any
        generalised or foundational artificial intelligence or machine learning model, and we do not use it for
        marketing or advertising. We disclose it only to the service providers needed to deliver those features,
        under terms that prohibit training on it.`,
      ],
    },
    {
      heading: 'Information Protection',
      paragraphs: [
        `We implement physical, business, and technical security measures to safeguard your personal information,
        including encryption in transit (TLS) and at rest where applicable, and we limit access to your data to those
        who need it to operate the Service. In the event of a security breach, we will notify you so that you can
        take appropriate protective steps, where we are required or reasonably able to do so.`,
        `We only keep your personal information for as long as is needed to provide the Service and fulfill the
        transactions you have requested, comply with our legal obligations, resolve disputes, and enforce our
        agreements. You can delete documents from your account, and we honor deletion requests. After that, we
        destroy it unless required by law.`,
      ],
    },
    {
      heading: 'Other Information',
      paragraphs: [
        `Because our retention needs can vary for different data types in different services, actual retention
        periods can vary based on criteria such as user expectations, the sensitivity of the data, the availability
        of controls that enable users to delete data, and our legal or contractual obligations.`,
        `As part of our normal operations, your information may be stored in computers in countries other than your
        home country. By giving us information, you consent to this kind of information transfer. Irrespective of
        where your information resides, we will comply with applicable law and abide by our commitments in this
        Policy.`,
        `We do not want your personal information if you are under 13. Do not provide it to us. If your child is
        under 13 and you believe your child has provided us with their personal information, contact us by email at
        uderstandnotes@gmail.com or through the Service so that we can remove it.`,
      ],
    },
    {
      heading: 'European Economic Area, United Kingdom, Swiss and California Users',
      paragraphs: [
        `The following rights are granted under the European General Data Protection Regulation ("GDPR") and the
        California Consumer Privacy Act ("CCPA"). We apply these rights to all users of our Service, regardless of
        location: the right to know what personal information is collected; the right to know if personal information
        is being shared, and with whom; the right to access your personal information; and the right to exercise your
        privacy rights without being discriminated against.`,
        `EEA, UK, and Swiss users. Our lawful bases for collecting and processing personal information include:
        performing our contract with you and providing the Service; our legitimate interests, such as receiving
        technical and interaction data to improve the security and reliability of the Service and prevent abuse; and
        consent, where we ask for it, which you may withdraw at any time. Under the GDPR you also have the right to
        request correction or erasure of personal information, the right to object to processing, the right to
        receive a copy of your personal information in a usable and portable format, and the right to lodge a
        complaint with a supervisory authority.`,
        `California users. Under the CCPA, California residents have the right to request deletion of personal
        information, subject to several exceptions, and the right to opt out of the sale of personal information. We
        do not "sell" personal information as defined by the CCPA and have not done so in the past 12 months. You may
        designate an authorized agent to make requests on your behalf; before accepting such a request, we will
        require the agent to provide proof that you have authorized it to act for you, and we may need you to verify
        your identity directly with us.`,
      ],
    },
    {
      heading: 'Cookies and Local Storage',
      paragraphs: [
        `We use browser local storage to keep you signed in and to store your session and preferences. We may use
        analytics cookies or similar technologies to understand how the Service is used. You can usually disable
        these through your browser settings, though some features may not work without them.`,
      ],
    },
    {
      heading: 'Changes',
      paragraphs: [
        `We may need to change this Privacy Policy from time to time. Any updates will be posted on this page with an
        effective date. Continued use of the Service after the effective date of any changes constitutes acceptance
        of those changes.`,
      ],
    },
    {
      heading: 'Contact',
      paragraphs: [
        `If you have questions or requests about this Policy or your personal information, you may contact us by
        email at uderstandnotes@gmail.com or through the contact options available within the Service.`,
      ],
    },
  ],
};

const TERMS_DOC: LegalDoc = {
  title: 'Terms of Service',
  updated: 'Last updated and effective date: 19 August 2026',
  intro: [
    `PLEASE READ THESE TERMS OF SERVICE ("TERMS") CAREFULLY BEFORE USING THE SERVICE OFFERED BY UNDERSTANDING
    NOTES ("WE", "US", OR "OUR"). THESE TERMS SET FORTH THE LEGALLY BINDING TERMS AND CONDITIONS FOR YOUR USE OF
    THE UNDERSTANDING NOTES WEBSITE AND ALL RELATED SERVICES, INCLUDING, WITHOUT LIMITATION, ANY FEATURES, CONTENT,
    WEBSITES, OR APPLICATIONS OFFERED FROM TIME TO TIME IN CONNECTION THEREWITH (COLLECTIVELY, THE "SERVICE"). BY
    USING THE SERVICE IN ANY MANNER, YOU AGREE TO BE BOUND BY THESE TERMS.`,
    `"The Site" refers to the website operated by Understanding Notes, as well as any associated applications,
    services, features, content, and functionalities offered by Understanding Notes.`,
  ],
  sections: [
    {
      heading: 'Acceptance of Terms of Service',
      paragraphs: [
        `The Service is offered subject to acceptance without modification of all of these Terms and all other
        operating rules, policies, and procedures that may be published from time to time in connection with the
        Service. Some services offered through the Service may be subject to additional terms and conditions
        promulgated from time to time; your use of such services is subject to those additional terms and
        conditions, which are incorporated into these Terms by this reference.`,
        `We may, in our sole discretion, refuse to offer the Service to any person or entity and change our
        eligibility criteria at any time. This provision is void where prohibited by law, and the right to access
        the Service is revoked in such jurisdictions.`,
      ],
    },
    {
      heading: 'Rules and Conduct',
      paragraphs: [
        `By using the Service, you agree that it is intended solely for lawful purposes, including understanding,
        summarizing, and analyzing documents that you own or are authorized to use. When you upload documents that
        contain information about other individuals, you confirm that you have the right and, where required,
        consent to process such information, and you are responsible for complying with applicable law.`,
        `By using the Service, you confirm that you are at least 18 years old, or have reached the legal age of
        majority in your country of residence. If you are under 18 or the legal age in your country (whichever is
        higher), you are prohibited from using the Service unless a parent or legal guardian agrees to these Terms
        on your behalf. It is your responsibility to ensure that you comply with your local laws regarding age
        restrictions for digital services.`,
        `As a condition of use, you promise not to use the Service for any purpose that is prohibited by these
        Terms. By way of example, and not as a limitation, you shall not (and shall not permit any third party to)
        take any action that: would constitute a violation of any applicable law, rule, or regulation; infringes
        upon any intellectual property or other right of any other person or entity; is threatening, abusive,
        harassing, defamatory, libelous, deceptive, fraudulent, invasive of another's privacy, tortious, obscene,
        offensive, or profane; exploits or abuses children; generates or disseminates verifiably false information
        with the purpose of harming others; impersonates or attempts to impersonate others; generates or
        disseminates personally identifying information without authorization; condones or promotes violence
        against people based on any protected legal category; or creates or distributes deepfake or manipulated
        content with the intent to deceive, defraud, or mislead others.`,
        `The Service is not designed to comply with industry-specific regulations, such as the Health Insurance
        Portability and Accountability Act (HIPAA) or the Federal Information Security Management Act (FISMA). Do
        not use the Service for data that would be subject to such laws.`,
        `Further, you shall not (directly or indirectly): (a) take any action that imposes or may impose an
        unreasonable or disproportionately large load on our (or our third-party providers') infrastructure; (b)
        interfere or attempt to interfere with the proper working of the Service or any activities conducted on the
        Service; (c) bypass any measures we may use to prevent or restrict access to the Service (or parts
        thereof); (d) use any method to extract data from the Service, including web scraping, web harvesting, or
        web data extraction methods, other than as permitted through an allowable API; (e) reverse assemble,
        reverse compile, decompile, translate, or otherwise attempt to discover the source code or underlying
        components of the Service that are not open, except to the extent such restrictions are contrary to
        applicable law; or (f) reproduce, duplicate, copy, sell, resell, or exploit any portion of the Site, use of
        the Site, or access to the Site, without our express written permission.`,
        `We reserve the right to monitor the Service for compliance with these Terms and to remove, refuse, or
        limit any content or output that we believe violates these Terms or applicable law. Accounts found to be in
        violation may be suspended or terminated, and we may report unlawful conduct to the relevant authorities
        where required by law.`,
      ],
    },
    {
      heading: 'DMCA and Takedowns Policy',
      paragraphs: [
        `The Service utilizes artificial intelligence systems to produce output. Such output may be unintentionally
        similar to copyright-protected material or trademarks held by others. We respect rights holders
        internationally and we ask our users to do the same.`,
        `If you believe in good faith that content on the Service infringes your copyright, you may submit a notice
        of alleged infringement by email at uderstandnotes@gmail.com or through the channels available within the
        Service. We will respond to valid notices and, in appropriate circumstances, terminate the accounts of
        repeat infringers.`,
      ],
    },
    {
      heading: 'Modification of Terms of Service',
      paragraphs: [
        `At our sole discretion, we may modify or replace any of these Terms, or change, suspend, or discontinue the
        Service (including, without limitation, the availability of any feature, database, or content) at any time
        by posting a notice on the Site. We may also impose limits on certain features and services or restrict
        your access to parts or all of the Service without notice or liability. It is your responsibility to check
        these Terms periodically for changes. Your continued use of the Service following the posting of any changes
        to these Terms constitutes acceptance of those changes.`,
      ],
    },
    {
      heading: 'Trademarks and Patents',
      paragraphs: [
        `All Understanding Notes logos, marks, and designations are trademarks or registered trademarks of
        Understanding Notes. All other trademarks mentioned on this website are the property of their respective
        owners. The trademarks and logos displayed on this website may not be used without our prior written consent
        or that of their respective owners.`,
      ],
    },
    {
      heading: 'Licensing Terms',
      paragraphs: [
        `Subject to your compliance with these Terms and any limitations applicable to us or by law: (a) you are
        granted a non-exclusive, limited, non-transferable, non-sublicensable, freely revocable license to access
        and use the Service for business or personal use; (b) you retain all rights in the documents and other
        content you upload ("Your Content"); and (c) you own the output generated for you through the Service, and
        you may use it for personal or commercial purposes. Otherwise, we reserve all rights not expressly granted
        under these Terms.`,
        `Each person must have a unique account, and you are responsible for any activity conducted on your
        account. A breach or violation of any of these Terms may result in immediate termination of your right to
        use the Service.`,
        `By using the Service, you grant us a limited, worldwide, non-exclusive, no-charge, royalty-free license to
        process, store, and use Your Content solely to provide, maintain, and improve the Service, to comply with
        applicable law, and to enforce our policies. This license does not include the right to train models on Your
        Content or to disclose Your Content except as described in our Privacy Policy.`,
      ],
    },
    {
      heading: 'Fees and Payments',
      paragraphs: [
        `The Service is offered on a free and paid basis as described on our pricing page. You can sign up for a
        monthly or yearly subscription, which will automatically renew for the same period after the agreed term
        unless you cancel before the renewal date. Because digital content and services are provided immediately
        upon purchase, fees are non-refundable and non-cancelable except as required by law. If you cancel your
        subscription, you will not receive a refund or credit for amounts already billed, and access continues until
        the end of the paid period.`,
        `Unless otherwise stated, your subscription fees do not include federal, state, local, and foreign taxes,
        duties, and other similar assessments. You are responsible for all taxes associated with your purchase, and
        we may invoice you for such taxes. If any amount of your fees is past due, we may suspend your access to the
        Service after providing you written notice of late payment.`,
        `We reserve the right to change our prices and offerings at any time. If you are on a subscription plan,
        changes to pricing will not apply until your next renewal. You may not create more than one account to
        benefit from the free tier of our Service, and if we believe you are not using the free tier in good faith,
        we may charge you standard fees or stop providing access to the Service.`,
      ],
    },
    {
      heading: 'Termination',
      paragraphs: [
        `We may terminate your access to all or any part of the Service at any time if you fail to comply with these
        Terms, which may result in the forfeiture and destruction of all information associated with your account.
        Further, either party may terminate the Service for any reason and at any time upon written notice. If you
        wish to terminate your account, you may do so through the Service. Any fees paid hereunder are
        non-refundable except as required by law.`,
        `Upon any termination, all rights and licenses granted to you in these Terms immediately terminate, but all
        provisions which by their nature should survive termination shall survive, including, without limitation,
        warranty disclaimers, indemnification, and limitations of liability.`,
      ],
    },
    {
      heading: 'Indemnification',
      paragraphs: [
        `You shall defend, indemnify, and hold harmless Understanding Notes, its affiliates, and each of their
        employees, contractors, directors, suppliers, and representatives from all liabilities, losses, claims,
        and expenses, including reasonable attorneys' fees, that arise from or relate to (a) your use or misuse of,
        or access to, the Service, or (b) your violation of these Terms or any applicable law, contract, policy,
        regulation, or other obligation. We reserve the right to assume the exclusive defense and control of any
        matter otherwise subject to indemnification by you, in which event you will assist and cooperate with us in
        connection therewith.`,
      ],
    },
    {
      heading: 'Limitation of Liability',
      paragraphs: [
        `IN NO EVENT SHALL WE OR OUR DIRECTORS, EMPLOYEES, AGENTS, PARTNERS, SUPPLIERS, OR CONTENT PROVIDERS BE
        LIABLE UNDER CONTRACT, TORT, STRICT LIABILITY, NEGLIGENCE, OR ANY OTHER LEGAL OR EQUITABLE THEORY WITH
        RESPECT TO THE SERVICE (a) FOR ANY LOST PROFITS, DATA LOSS, COST OF PROCUREMENT OF SUBSTITUTE GOODS OR
        SERVICES, OR SPECIAL, INDIRECT, INCIDENTAL, PUNITIVE, OR CONSEQUENTIAL DAMAGES OF ANY KIND WHATSOEVER, (b)
        FOR YOUR RELIANCE ON THE SERVICE OR ANY OUTPUT, OR (c) FOR ANY DIRECT DAMAGES IN EXCESS (IN THE AGGREGATE)
        OF THE FEES PAID BY YOU FOR THE SERVICE IN THE TWELVE MONTHS PRECEDING THE CLAIM OR, IF GREATER, $500. SOME
        JURISDICTIONS DO NOT ALLOW THE EXCLUSION OR LIMITATION OF INCIDENTAL OR CONSEQUENTIAL DAMAGES, SO THE ABOVE
        LIMITATIONS AND EXCLUSIONS MAY NOT APPLY TO YOU.`,
      ],
    },
    {
      heading: 'Disclaimer',
      paragraphs: [
        `ALL USE OF THE SERVICE AND ANY CONTENT OR OUTPUT IS UNDERTAKEN ENTIRELY AT YOUR OWN RISK. THE SERVICE IS
        PROVIDED "AS IS" AND "AS AVAILABLE" AND IS WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING, BUT
        NOT LIMITED TO, THE IMPLIED WARRANTIES OF TITLE, NON-INFRINGEMENT, MERCHANTABILITY, AND FITNESS FOR A
        PARTICULAR PURPOSE, AND ANY WARRANTIES IMPLIED BY ANY COURSE OF PERFORMANCE OR USAGE OF TRADE, ALL OF WHICH
        ARE EXPRESSLY DISCLAIMED. WE MAKE NO WARRANTY THAT THE SERVICE WILL MEET YOUR REQUIREMENTS, THAT ACCESS TO
        AND USE OF THE SERVICE WILL BE UNINTERRUPTED, TIMELY, SECURE, OR ERROR-FREE, OR THAT ANY OUTPUT WILL BE
        ACCURATE, COMPLETE, OR RELIABLE.`,
        `The Service uses AI to generate answers, summaries, and other output. AI output can be inaccurate,
        incomplete, or outdated. While we provide citations to sources, we do not guarantee that any output is
        correct, complete, unique, or confidential, and you are responsible for verifying any output before relying
        on it. The Service is not a substitute for professional legal, medical, financial, or other expert advice,
        and you should not use output to make decisions where inaccuracy could cause harm.`,
      ],
    },
    {
      heading: 'Age Requirements',
      paragraphs: [
        `By accessing the Service, you confirm that you are at least 18 years old and meet the minimum age of
        digital consent in your country. If you are not old enough to consent to these Terms in your country, your
        parent or guardian must agree to these Terms on your behalf. If you are a parent or legal guardian and you
        allow your teenager to use the Service, then these Terms also apply to you, and you are responsible for
        your teenager's activity on the Service. No assurances are made as to the suitability of any output for
        you.`,
      ],
    },
    {
      heading: 'Miscellaneous',
      paragraphs: [
        `These Terms are the entire agreement between you and us with respect to the Service and supersede all prior
        or contemporaneous communications and proposals (whether oral, written, or electronic) between you and us
        with respect to the Service. If any provision of these Terms is found to be unenforceable or invalid, that
        provision will be limited or eliminated to the minimum extent necessary so that these Terms will otherwise
        remain in full force and effect.`,
        `The failure of either party to exercise in any respect any right provided for herein shall not be deemed a
        waiver of any further rights hereunder. We shall not be liable for any failure to perform our obligations
        hereunder due to any cause beyond our reasonable control. These Terms are personal to you and are not
        assignable or transferable by you except with our prior written consent. We may assign, transfer, or
        delegate any of our rights and obligations hereunder without consent. No agency, partnership, joint venture,
        or employment relationship is created as a result of these Terms, and neither party has any authority of
        any kind to bind the other in any respect.`,
      ],
    },
    {
      heading: 'Your Rights to Use the Site; Our Content and Intellectual Property Rights',
      paragraphs: [
        `Subject to these Terms, we grant you a limited, non-exclusive, revocable, and personal license to access
        and use the Site solely for informational purposes.`,
        `Unless otherwise expressly indicated, all content displayed or made available on the Site, including,
        without limitation, text, images, illustrations, designs, logos, domain names, service marks, software,
        scripts, and the selection, compilation, and arrangement of any of the foregoing, is owned by us, our
        affiliates, licensors, and/or other third parties. The Site and all such content are protected by copyright,
        trade dress, trademark, moral rights, and other intellectual property laws. All such rights are reserved.
        Nothing displayed or accessed in connection with the Site shall be construed as granting, by implication,
        estoppel, or otherwise, any license or right to use any trademark, logo, or service mark displayed in
        connection with the Site without the owner's prior written permission.`,
      ],
    },
    {
      heading: 'Prohibited Uses',
      paragraphs: [
        `You are fully responsible for your activities while using the Site, including any content or other
        materials you post or upload, and you bear all risks associated with the use of the Site. You agree to
        comply with all applicable laws and regulations in connection with your use of the Site.`,
        `We reserve the right (but not the obligation), in our sole discretion, to (a) monitor the Site for
        violations of these Terms; (b) take appropriate legal action against anyone who uses or accesses the Site
        in a manner that we believe violates the law or these Terms, including, without limitation, reporting such
        user to law enforcement authorities; (c) deny access to the Site or any features of the Site to anyone who
        violates these Terms or who we believe interferes with the ability of others to enjoy the Site or infringes
        the rights of others; and (d) otherwise manage the Site in a manner designed to protect our rights and
        property and to facilitate the proper functioning of the Site.`,
        `You are prohibited from using the Site for harmful or illegal activities. Accordingly, you may not, or
        assist any other person to: violate these Terms or other policies posted on the Site; include sensitive
        personal information (such as phone numbers, residential addresses, health information, social security
        numbers, driver's license numbers, or other account numbers) about yourself or any other person in any
        webform on the Site; copy or adapt the Site's software or code; upload any material containing a virus,
        worm, spyware, Trojan horse, or other program designed to interrupt, destroy, or limit the functionality of
        the Site; use, launch, develop, or distribute any automated system, including any spider, robot, scraper,
        offline reader, or data-mining tool to access the Site; interfere with, disable, vandalise, or disrupt the
        Site or servers or networks connected to the Site; hack into, penetrate, disable, or otherwise circumvent
        the security measures of the Site; impersonate another person or falsely represent an affiliation with any
        organisation or institution; use the Site in any way that violates any applicable law or regulation; or
        attempt to do any of the above.`,
      ],
    },
    {
      heading: 'DMCA Copyright Infringement Notice',
      paragraphs: [
        `We have implemented procedures consistent with the Digital Millennium Copyright Act of 1998 ("DMCA"), 17
        U.S.C. § 512, regarding the reporting of alleged copyright infringement and the removal of, or disabling
        access to, infringing material. If you have a good faith belief that copyrighted material on the Site is
        being used in a way that infringes the copyright over which you are authorized to act, you may submit a
        Notice of Infringing Material by email at uderstandnotes@gmail.com or through the channels available within
        the Service. Before serving a notice, you may wish to contact a lawyer to better understand your rights and
        obligations under the DMCA and other applicable laws, and any notice that fails to comply with the
        requirements of section 512(c)(3) may not be effective.`,
      ],
    },
    {
      heading: 'Termination of Repeat Infringers',
      paragraphs: [
        `We will terminate or disable the accounts of users who are deemed, in appropriate circumstances, to be
        repeat copyright infringers.`,
      ],
    },
    {
      heading: 'Links to and From Other Websites',
      paragraphs: [
        `You may gain access to other websites via links on the Site. These Terms apply to the Site only and do not
        apply to other parties' websites. We assume no responsibility for any terms of service or material outside
        of the Site accessed via any link. You are free to establish a hypertext link to the Site so long as the
        link does not state or imply any sponsorship of your website or service by us. You may not, without our
        prior written permission, frame or inline link any of the content of the Site, scrape the Site, or
        incorporate into another website or service any of our material, content, or intellectual property.`,
      ],
    },
    {
      heading: 'Dispute Resolution by Binding Arbitration',
      paragraphs: [
        `PLEASE READ THIS SECTION CAREFULLY, AS IT AFFECTS YOUR RIGHTS. You and we agree that any and all disputes,
        claims, demands, or causes of action that have arisen or may arise between you and us, whether arising out
        of or relating to these Terms, the Site, or any aspect of the relationship between us, will be resolved
        exclusively through final and binding arbitration before a neutral arbitrator, rather than in court by a
        judge or jury, except that you or we may elect to assert individual claims in small claims court if such
        claims are within the scope of such court's jurisdiction.`,
        `By entering into these Terms, you and we are each waiving the right to a trial by jury and the right to
        participate in a class action. Each of us may bring claims against the other only on an individual basis and
        not as a plaintiff or class member in any purported class or representative action or proceeding.`,
        `Before initiating arbitration, you agree to try to resolve the dispute informally by contacting us by email
        at uderstandnotes@gmail.com or through the Service. If we cannot resolve the dispute within 30 days, either
        party may initiate arbitration. The
        arbitration will be conducted by a neutral arbitrator selected by agreement of the parties or, if the
        parties cannot agree, appointed in accordance with the rules of an independent arbitration institution. The
        arbitrator will issue a reasoned written decision sufficient to explain the essential findings and
        conclusions on which any award is based.`,
        `Payment of filing, administration, and arbitrator fees will be allocated in accordance with the rules of
        the applicable arbitration institution, provided that if you demonstrate that the costs of arbitration will
        be prohibitive as compared to the costs of litigation, we will pay as much of the arbitration fees as the
        arbitrator deems necessary to prevent the arbitration from being cost-prohibitive. Each party shall
        maintain the confidential nature of the arbitration, including all aspects of the proceeding and any ruling
        or award, except as necessary to enforce or challenge the award in a court of competent jurisdiction or as
        otherwise required by law.`,
        `You may reject this arbitration provision by sending us an opt-out notice by email at uderstandnotes@gmail.com
        or through the Service within 30 days after you first use the Service. Opting out will not affect any other
        aspect of these Terms. If any
        part of this arbitration provision is found to be invalid or unenforceable, the remainder will be
        enforceable as modified to the extent consistent with the parties' intent, except that the prohibition on
        class and representative actions may not be severed, and if that prohibition is found unenforceable, this
        entire arbitration provision will be null and void.`,
      ],
    },
    {
      heading: 'Governing Law',
      paragraphs: [
        `Except as otherwise required by applicable law, these Terms are governed by the laws of the jurisdiction in
        which you reside, without regard to conflict-of-law principles. Except as provided in the Dispute
        Resolution by Binding Arbitration section, all claims will be brought in the competent courts of your
        jurisdiction, and you consent to the jurisdiction of those courts.`,
      ],
    },
    {
      heading: 'Changes to These Terms',
      paragraphs: [
        `We may change or modify these Terms by posting a revised version on the Site or by otherwise providing
        notice to you, and we will state at the top of the revised Terms the date they were last revised. Changes
        will not apply retroactively and will become effective no earlier than fourteen (14) calendar days after
        they are posted, except for changes made for legal reasons, which will be effective immediately. Your
        continued use of the Site after any change means you agree to the new Terms.`,
      ],
    },
    {
      heading: 'Privacy',
      paragraphs: [
        `Our commitment to privacy and data protection is reflected in our Privacy Policy, which is incorporated
        into these Terms by reference. Please review it carefully. By using the Service, you consent to the
        collection, use, and sharing of your information as described in our Privacy Policy.`,
      ],
    },
  ],
};

@Component({
  selector: 'app-legal',
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './legal.component.html',
  styleUrl: './legal.component.scss'
})
export class LegalComponent {
  private readonly route = inject(ActivatedRoute);

  protected readonly doc: LegalDoc =
    this.route.snapshot.data['legal'] === 'terms' ? TERMS_DOC : PRIVACY_DOC;
}
