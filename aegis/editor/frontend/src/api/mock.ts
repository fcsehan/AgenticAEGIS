import type { Domain, Project, MeldFile } from "@/types/domain";

/**
 * Mock data derived from the actual .meld files in IAMissionProject/.
 *
 * Source: IAMissionObligationVocabMt.meld — DASSA Cyber Command & Control spec (v0.9).
 * Deontic vocabulary: DeonticReasoningWithMultiFuture-LogicMt.meld
 *   - oughtToDo-WRT(CODE, AGT, PROP)
 *   - forbiddenToDo-WRT(CODE, AGT, PROP)
 *   - permittedToDo-WRT(CODE, AGT, PROP)
 */

const iaMissionMeldFiles: MeldFile[] = [
  {
    path: "meld/DeonticReasoning-LogicMt.meld",
    name: "DeonticReasoning-LogicMt",
    type: "vocabulary",
    sizeBytes: 7200,
  },
  {
    path: "meld/DeonticReasoningWithMultiFuture-LogicMt.meld",
    name: "DeonticReasoningWithMultiFuture-LogicMt",
    type: "vocabulary",
    sizeBytes: 18700,
  },
  {
    path: "meld/DeonticReasoning-InferenceMt.meld",
    name: "DeonticReasoning-InferenceMt",
    type: "inference",
    sizeBytes: 2400,
  },
  {
    path: "meld/IAMissionObligationVocabMt.meld",
    name: "IAMissionObligationVocabMt",
    type: "deontic",
    sizeBytes: 15000,
  },
];

// ── Roles: MissionSupportRole instances from IAMissionObligationVocabMt ──

const iaMissionDomain: Domain = {
  id: "ia-mission",
  name: "IA Mission Obligations",
  description:
    "Joint Staff obligation vocabulary for mission-critical contexts (DASSA Cyber C2 spec v0.9). Defines MissionSupportRoles, JointStaffResponsibilityTypes, and their deontic bindings via oughtToDo-WRT / forbiddenToDo-WRT.",
  status: "Published",
  roles: [
    {
      id: "commanderInMission",
      name: "commanderInMission",
      description:
        "Commander in charge of planning and carrying out the mission. Every mission is assigned to a commander, who is also the commander of the largest unit charged with carrying out the mission.",
      ruleCount: 2,
    },
    {
      id: "manPowerAndPersonnelAgentInMission",
      name: "manPowerAndPersonnelAgentInMission",
      description:
        "Provides manpower and personnel support. Responsibilities include managing manpower, formulating personnel policies, and supervising administration of personnel, including civilians and prisoners of war.",
      obligationType: "J1Obligation",
      ruleCount: 3,
    },
    {
      id: "intelligenceAgentInMission",
      name: "intelligenceAgentInMission",
      description:
        "Intelligence provider. Responsibilities include insuring availability of sound intelligence, directing intelligence efforts on proper enemy items of interest, and disclosing enemy capabilities and intentions.",
      obligationType: "J2Obligation",
      ruleCount: 3,
    },
    {
      id: "operationsAgentInMission",
      name: "operationsAgentInMission",
      description:
        "Provides operations support. Responsibilities include assisting in the direction and control of unit operations, and planning, coordinating, and integrating operations.",
      obligationType: "J3Obligation",
      ruleCount: 2,
    },
    {
      id: "logisticsAgentInMission",
      name: "logisticsAgentInMission",
      description:
        "Provides logistics support. Responsibilities include formulating logistics plans, coordinating logistics-related matters, and insuring effective logistics support for all forces in the command.",
      obligationType: "J4Obligation",
      ruleCount: 3,
    },
    {
      id: "planningAndPolicyAgentInMission",
      name: "planningAndPolicyAgentInMission",
      description:
        "Provides planning and policy support. Responsibilities include assisting the commander in long-range or future planning, preparing operation and campaign plans including COAs, and preparing situational estimates.",
      obligationType: "J5Obligation",
      ruleCount: 3,
    },
    {
      id: "c4AgentInMission",
      name: "c4AgentInMission",
      description:
        "Provides command, control, communications, and computers (C4) support. Responsibilities include assisting the commander with communications-electronics and automated data systems, and furnishing communications to exercise command.",
      obligationType: "J6Obligation",
      ruleCount: 3,
    },
    {
      id: "personalStaffAgentInMission",
      name: "personalStaffAgentInMission",
      description:
        "Provides personal staff support. Responsibilities include political advice and assisting the commander with special matters over which the commander chooses to exercise close personal control.",
      obligationType: "PersonalStaffObligation",
      ruleCount: 1,
    },
    {
      id: "specialStaffAgentInMission",
      name: "specialStaffAgentInMission",
      description:
        "Provides special staff support. Responsibilities include giving technical, administrative, and tactical advice, preparing plan components, estimates, and orders, and coordinating and supervising staff activities.",
      obligationType: "SpecialStaffObligation",
      ruleCount: 2,
    },
  ],
  obligationTypes: [
    {
      id: "JointStaffResponsibilityType",
      name: "JointStaffResponsibilityType",
      description:
        "Type-level collection. Instances are collections of Obligation instances corresponding to Functions of Joint Staff Divisions (DASSA Cyber C2 spec p.7, v0.9).",
      children: [
        {
          id: "J1Obligation",
          name: "J1Obligation",
          description:
            "Manpower & Personnel: manage manpower, formulate personnel policy, supervise administration of personnel including civilians and POWs.",
          parentId: "JointStaffResponsibilityType",
          children: [],
        },
        {
          id: "J2Obligation",
          name: "J2Obligation",
          description:
            "Intelligence: insure availability of sound intelligence, direct intelligence efforts, disclose threat force capabilities and intentions.",
          parentId: "JointStaffResponsibilityType",
          children: [],
        },
        {
          id: "J3Obligation",
          name: "J3Obligation",
          description:
            "Operations: assist in the direction, control, and planning of operations.",
          parentId: "JointStaffResponsibilityType",
          children: [],
        },
        {
          id: "J4Obligation",
          name: "J4Obligation",
          description:
            "Logistics: formulate logistics plans, coordinate logistics-related matters, insure effective logistics support for all forces.",
          parentId: "JointStaffResponsibilityType",
          children: [],
        },
        {
          id: "J5Obligation",
          name: "J5Obligation",
          description:
            "Plans & Policy: assist in long-range or future planning, prepare situation estimates and COAs.",
          parentId: "JointStaffResponsibilityType",
          children: [],
        },
        {
          id: "J6Obligation",
          name: "J6Obligation",
          description:
            "C4: assist with communications-electronics and automated data systems, prepare communications plans, furnish communications for command.",
          parentId: "JointStaffResponsibilityType",
          children: [],
        },
      ],
    },
    {
      id: "PersonalStaffObligation",
      name: "PersonalStaffObligation",
      description:
        "Personal Staff: maintain capability to deal with special matters under commander's personal control.",
      children: [],
    },
    {
      id: "SpecialStaffObligation",
      name: "SpecialStaffObligation",
      description:
        "Special Staff: maintain capability for technical, administrative, and tactical advice; prepare plan components, estimates, and orders.",
      children: [],
    },
  ],
  codes: [
    {
      id: "JointStaffDoctrine",
      name: "Joint Staff Doctrine",
      description:
        "Primary CodeOfConduct governing joint staff obligations. All oughtToDo-WRT and forbiddenToDo-WRT assertions reference this code.",
      prevalence: 1,
    },
  ],

  // ── NormFrames derived from obligation definitions in IAMissionObligationVocabMt ──
  // These represent the deontic assertions extracted by the MELD Loader using
  // the -WRT predicates: (oughtToDo-WRT JointStaffDoctrine AGENT PROP)

  rules: [
    // J1 — Manpower & Personnel
    {
      id: "j1-manage-manpower",
      code: "JointStaffDoctrine",
      agentRole: "manPowerAndPersonnelAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(supportFromPlayer manPowerAndPersonnelAgentInMission ManPowerAndPersonnelSupport)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:193",
    },
    {
      id: "j1-formulate-personnel-policy",
      code: "JointStaffDoctrine",
      agentRole: "manPowerAndPersonnelAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(PolicyFormulationFn (PolicyConcernsFn MilitaryPerson))",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:30",
    },
    {
      id: "j1-supervise-admin-personnel",
      code: "JointStaffDoctrine",
      agentRole: "manPowerAndPersonnelAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(activityTypeSupervised AdministeringPersonnel)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:192",
    },

    // J2 — Intelligence
    {
      id: "j2-provide-intelligence",
      code: "JointStaffDoctrine",
      agentRole: "intelligenceAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(supportFromPlayer intelligenceAgentInMission IntelligenceSupport)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:124",
    },
    {
      id: "j2-direct-intelligence-efforts",
      code: "JointStaffDoctrine",
      agentRole: "intelligenceAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(directIntelligenceEffortsOnProperItems intelligenceAgentInMission)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:43",
    },
    {
      id: "j2-disclose-enemy-capabilities",
      code: "JointStaffDoctrine",
      agentRole: "intelligenceAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(discloseCapabilitiesAndIntentions ThreatForce)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:43",
    },

    // J3 — Operations
    {
      id: "j3-support-operations",
      code: "JointStaffDoctrine",
      agentRole: "operationsAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(supportFromPlayer operationsAgentInMission OperationsSupport)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:32",
    },
    {
      id: "j3-direct-control-operations",
      code: "JointStaffDoctrine",
      agentRole: "operationsAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(assistInDirectionAndControlOfOperations operationsAgentInMission)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:208",
    },

    // J4 — Logistics
    {
      id: "j4-provide-logistics",
      code: "JointStaffDoctrine",
      agentRole: "logisticsAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(supportFromPlayer logisticsAgentInMission LogisticsSupport)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:88",
    },
    {
      id: "j4-formulate-logistics-plans",
      code: "JointStaffDoctrine",
      agentRole: "logisticsAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(formulateLogisticsPlans logisticsAgentInMission)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:155",
    },
    {
      id: "j4-insure-logistics-support",
      code: "JointStaffDoctrine",
      agentRole: "logisticsAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(insureEffectiveLogisticsSupportForAllForces logisticsAgentInMission)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:132",
    },

    // J5 — Plans & Policy
    {
      id: "j5-provide-planning",
      code: "JointStaffDoctrine",
      agentRole: "planningAndPolicyAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(supportFromPlayer planningAndPolicyAgentInMission PlanningAndPolicySupport)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:166",
    },
    {
      id: "j5-prepare-estimates-coas",
      code: "JointStaffDoctrine",
      agentRole: "planningAndPolicyAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(prepareSituationEstimatesAndCOAs planningAndPolicyAgentInMission)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:57",
    },
    {
      id: "j5-assist-long-range-planning",
      code: "JointStaffDoctrine",
      agentRole: "planningAndPolicyAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(assistInLongRangePlanning planningAndPolicyAgentInMission)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:142",
    },

    // J6 — C4
    {
      id: "j6-provide-c4",
      code: "JointStaffDoctrine",
      agentRole: "c4AgentInMission",
      modality: "OBLIGATORY",
      proposition: "(supportFromPlayer c4AgentInMission C4Support)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:80",
    },
    {
      id: "j6-prepare-comm-plans",
      code: "JointStaffDoctrine",
      agentRole: "c4AgentInMission",
      modality: "OBLIGATORY",
      proposition: "(prepareCommAndDataSystemsPlans c4AgentInMission)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:111",
    },
    {
      id: "j6-furnish-communications",
      code: "JointStaffDoctrine",
      agentRole: "c4AgentInMission",
      modality: "OBLIGATORY",
      proposition: "(furnishCommunicationsForCommand c4AgentInMission)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:74",
    },

    // Commander
    {
      id: "cmd-assigned-to-mission",
      code: "JointStaffDoctrine",
      agentRole: "commanderInMission",
      modality: "OBLIGATORY",
      proposition: "(planAndCarryOutMission (CommanderInMissionFn Mission))",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:66",
    },
    {
      id: "cmd-single-entry",
      code: "JointStaffDoctrine",
      agentRole: "commanderInMission",
      modality: "FORBIDDEN",
      proposition: "(multipleCommandersInMission Mission)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:128",
    },

    // Personal Staff
    {
      id: "ps-special-matters",
      code: "JointStaffDoctrine",
      agentRole: "personalStaffAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(maintainCapabilityForSpecialMattersUnderCommanderControl personalStaffAgentInMission)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:63",
    },

    // Special Staff
    {
      id: "ss-technical-advice",
      code: "JointStaffDoctrine",
      agentRole: "specialStaffAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(provideTechnicalAdministrativeTacticalAdvice specialStaffAgentInMission)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:96",
    },
    {
      id: "ss-prepare-plans",
      code: "JointStaffDoctrine",
      agentRole: "specialStaffAgentInMission",
      modality: "OBLIGATORY",
      proposition: "(preparePlanComponentsEstimatesAndOrders specialStaffAgentInMission)",
      specificity: 1,
      defeasible: false,
      source: "IAMissionObligationVocabMt.meld:96",
    },
  ],
  conflictCount: 0,
  lastModified: "2026-03-20T10:00:00Z",
  version: "1.0.0",
};

/** Mock project registry — maps directory paths to resolved projects. */
const mockProjects: Record<string, Project> = {
  "/workspace/IAMissionProject": {
    path: "/workspace/IAMissionProject",
    name: "IAMissionProject",
    meldFiles: iaMissionMeldFiles,
    domains: [iaMissionDomain],
    loadedAt: new Date().toISOString(),
  },
};

/** Legacy export for existing tests. */
export const mockDomains: Domain[] = [iaMissionDomain];

export { mockProjects, iaMissionDomain, iaMissionMeldFiles };
