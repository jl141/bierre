/**
 * Privacy Policy view
 * /privacy route.
 */

import { h } from "../lib/dom.js";

/**
 * @param {Object} options
 * @param {{get: function(): Object, set: function(Object): void}} options.store
 * @returns {{mount: function(HTMLElement): void, unmount: function(): void}}
 */
export function createPrivacyView() {
  let element = null;

  const sections = [
    {
      title: "Purpose",
      blocks: [
        {
          type: "paragraph",
          text: 'The purpose of this privacy policy (this "Privacy Policy") is to inform users of our Site of the following:',
        },
        {
          type: "list",
          items: [
            "The personal data we will collect;",
            "Use of collected data;",
            "Who has access to the data collected; and",
            "The rights of Site users.",
          ],
        },
        {
          type: "paragraph",
          text: "This Privacy Policy applies in addition to the terms and conditions of our Site.",
        },
      ],
    },
    {
      title: "Consent",
      blocks: [
        {
          type: "paragraph",
          text: "By using our Site users agree that they consent to:",
        },
        {
          type: "list",
          items: [
            "The conditions set out in this Privacy Policy; and",
            "The collection, use, and retention of the data listed in this Privacy Policy.",
          ],
        },
      ],
    },
    {
      title: "Personal Data We Collect",
      blocks: [
        {
          type: "paragraph",
          text: "We only collect data that helps us achieve the purpose set out in this Privacy Policy. We will not collect any additional data beyond the data listed below without notifying you first.",
        },
        { type: "subheading", text: "Data Collected Automatically" },
        {
          type: "paragraph",
          text: "When you visit and use our Site, we may automatically collect and store the following information:",
        },
        {
          type: "list",
          items: [
            "IP address;",
            "Location; and",
            "Hardware and software details.",
          ],
        },
        { type: "subheading", text: "Data Collected in a Non-Automatic Way" },
        {
          type: "paragraph",
          text: "We may also collect the following data when you perform certain functions on our Site:",
        },
        { type: "list", items: ["Email address."] },
        {
          type: "paragraph",
          text: "This data may be collected using the following methods:",
        },
        { type: "list", items: ["Creating an account."] },
      ],
    },
    {
      title: "How We Use Personal Data",
      blocks: [
        {
          type: "paragraph",
          text: "Data collected on our Site will only be used for the purposes specified in this Privacy Policy or indicated on the relevant pages of our Site. We will not use your data beyond what we disclose in this Privacy Policy.",
        },
        {
          type: "paragraph",
          text: "The data we collect automatically is used for the following purposes:",
        },
        { type: "list", items: ["Statistics; and", "Debugging."] },
        {
          type: "paragraph",
          text: "The data we collect when the user performs certain functions may be used for the following purposes:",
        },
        { type: "list", items: ["Human verification; and", "Communication."] },
      ],
    },
    {
      title: "Who We Share Personal Data With",
      blocks: [
        { type: "subheading", text: "Employees" },
        {
          type: "paragraph",
          text: "We may disclose user data to any member of our organization who reasonably needs access to user data to achieve the purposes set out in this Privacy Policy.",
        },
        { type: "subheading", text: "Other Disclosures" },
        {
          type: "paragraph",
          text: "We will not sell or share your data with other third parties, except in the following cases:",
        },
        {
          type: "list",
          items: [
            "If the law requires it;",
            "If it is required for any legal proceeding;",
            "To prove or protect our legal rights; and",
            "To buyers or potential buyers of this company in the event that we seek to sell the company.",
          ],
        },
        {
          type: "paragraph",
          text: "If you follow hyperlinks from our Site to another site, please note that we are not responsible for and have no control over their privacy policies and practices.",
        },
      ],
    },
    {
      title: "How Long We Store Personal Data",
      blocks: [
        { type: "paragraph", text: "User data will be stored for thirty days." },
        {
          type: "paragraph",
          text: "You will be notified if your data is kept for longer than this period.",
        },
      ],
    },
    {
      title: "How We Protect Your Personal Data",
      blocks: [
        {
          type: "paragraph",
          text: "In order to protect your security, we use the strongest available browser encryption and store all of our data on servers in secure facilities. All data is only accessible to our employees. Our employees are bound by strict confidentiality agreements and a breach of this agreement would result in the employee's termination.",
        },
        {
          type: "paragraph",
          text: "While we take all reasonable precautions to ensure that user data is secure and that users are protected, there always remains the risk of harm. The Internet as a whole can be insecure at times and therefore we are unable to guarantee the security of user data beyond what is reasonably practical.",
        },
      ],
    },
    {
      title: "Children",
      blocks: [
        {
          type: "paragraph",
          text: "We do not knowingly collect or use personal data from children under 13 years of age. If we learn that we have collected personal data from a child under 13 years of age, the personal data will be deleted as soon as possible. If a child under 13 years of age has provided us with personal data their parent or guardian may contact us.",
        },
      ],
    },
    {
      title: "How to Access, Modify, Delete, or Challenge the Data Collected",
      blocks: [
        {
          type: "paragraph",
          text: "If you would like to know if we have collected your personal data, how we have used your personal data, if we have disclosed your personal data and to who we disclosed your personal data, or if you would like your data to be deleted or modified in any way, please contact us here:",
        },
        { type: "email" },
      ],
    },
    {
      title: "Do Not Track Notice",
      blocks: [
        {
          type: "paragraph",
          text: 'Do Not Track ("DNT") is a privacy preference that you can set in certain web browsers. We do not track the users of our Site over time and across third party websites and therefore do not respond to browser-initiated DNT signals.',
        },
      ],
    },
    {
      title: "Modifications",
      blocks: [
        {
          type: "paragraph",
          text: 'This Privacy Policy may be amended from time to time in order to maintain compliance with the law and to reflect any changes to our data collection process. When we amend this Privacy Policy we will update the "Effective Date" at the top of this Privacy Policy. We recommend that our users periodically review our Privacy Policy to ensure that they are notified of any updates. If necessary, we may notify users by email of changes to this Privacy Policy.',
        },
      ],
    },
    {
      title: "Contact Information",
      blocks: [
        {
          type: "paragraph",
          text: "If you have any questions, concerns or complaints, you can contact:",
        },
        { type: "email" },
      ],
    },
  ];

  function renderBlock(block) {
    if (block.type === "list") {
      return h(
        "ol",
        { class: "body" },
        block.items.map((item) => h("li", null, item)),
      );
    }

    if (block.type === "subheading") {
      return h("h3", { class: "panel-subtitle" }, block.text);
    }

    if (block.type === "email") {
      return h(
        "p",
        { class: "body" },
        h("a", { href: "mailto:jul14nl1u@gmail.com" }, "jul14nl1u@gmail.com"),
      );
    }

    return h("p", { class: "body" }, block.text);
  }

  function build() {
    const privacyPanel = h(
      "section",
      { class: "panel", id: "privacy-panel" },
      h("h1", { class: "panel-title" }, "BIERRE PRIVACY POLICY"),
      h("p", { class: "view-intro" }, "Type of website: Scholarly Search Website"),
      h("p", { class: "body" }, "Effective date: 16th day of September, 2026"),
      h(
        "p",
        { class: "body" },
        'Bierre (the "Site") is owned and operated by Julian Liu. Julian can be contacted at:',
      ),
      h(
        "p",
        { class: "body" },
        h("a", { href: "mailto:jul14nl1u@gmail.com" }, "jul14nl1u@gmail.com"),
      ),
      sections.map((section) =>
        h(
          "section",
          { class: "body-section" },
          h("h2", { class: "panel-title" }, section.title),
          section.blocks.map(renderBlock),
        ),
      ),
    );

    return h("div", { class: "view" }, privacyPanel);
  }

  return {
    mount(outlet) {
      if (!element) element = build();
      outlet.append(element);
    },

    unmount() {},
  };
}