"""Synthetic host documents (English and German) that payloads are planted into.

The texts are written for this benchmark. Fictional names, no real organisations. Each genre
has a title bank, an author/header bank and sentence banks; a seeded RNG composes pages.
"""

from __future__ import annotations

import random

GENRES = ("paper", "cv", "memo", "datasheet")

TEXT = {
    "en": {
        "paper": {
            "titles": [
                "Robust Estimation of Sparse Signals under Adversarial Noise",
                "Graph Neural Networks for Traffic Forecasting in Mid-Sized Cities",
                "A Comparative Study of Tokenizers for Low-Resource Languages",
                "Energy-Efficient Scheduling for Edge Inference Clusters",
                "Learning Calibrated Uncertainty for Medical Image Segmentation",
            ],
            "header": ["A. Lindqvist, M. Okafor, J. Brandt", "R. Moreau and T. Hayashi", "S. Patel, L. Kowalski, D. Mensah"],
            "sentences": [
                "We study the problem of estimating a sparse vector from a small number of noisy linear measurements.",
                "Our method builds on convex relaxations and achieves competitive recovery guarantees.",
                "Experiments on three public benchmarks confirm the theoretical findings.",
                "We release our code and preprocessing scripts to support reproducibility.",
                "Prior work has focused on the noiseless setting, which rarely holds in practice.",
                "The proposed estimator is computationally efficient and easy to implement.",
                "We discuss limitations of the approach and outline directions for future work.",
                "All hyperparameters were selected on a held-out validation split.",
                "The results remain stable across five random seeds.",
                "Section 2 reviews related work, and Section 3 introduces the model.",
                "Ablation studies show that both components contribute to the final performance.",
                "We thank the anonymous reviewers for their helpful comments.",
            ],
        },
        "cv": {
            "titles": ["Curriculum Vitae", "Résumé", "Professional Profile"],
            "header": ["Jordan Ellison · Data Engineer", "Priya Raman · Product Designer", "Tomás Herrera · Backend Developer"],
            "sentences": [
                "Five years of experience building data pipelines for logistics and retail clients.",
                "Led the migration of a legacy reporting stack to a cloud data warehouse.",
                "Skills: Python, SQL, Airflow, Docker, stakeholder communication.",
                "M.Sc. in Computer Science, graduated with distinction.",
                "Mentored three junior engineers and introduced code review guidelines.",
                "Reduced nightly batch runtime by forty percent through query optimisation.",
                "Languages: English (native), Spanish (fluent), German (basic).",
                "Volunteer instructor for an introductory programming course.",
                "Certified in agile project management.",
                "References available on request.",
            ],
        },
        "memo": {
            "titles": ["Internal Memo: Quarterly Status", "Project Update – Warehouse Automation", "Meeting Notes: Vendor Review"],
            "header": ["To: Operations team · From: K. Brooks", "To: Steering committee · From: Project office", "Distribution: Finance, Procurement"],
            "sentences": [
                "The rollout of the new scanning devices is on schedule for the end of the quarter.",
                "Two vendors submitted complete offers; the third requested an extension.",
                "Budget utilisation stands at sixty-two percent of the annual plan.",
                "Training sessions for the night shift will take place next week.",
                "Please submit open invoices before the end of the month.",
                "The safety audit found no critical issues.",
                "We expect delivery delays of up to two weeks for spare parts.",
                "The next review meeting is scheduled for the first Monday of the month.",
                "Action items are listed in the attached spreadsheet.",
                "Questions can be directed to the project office.",
            ],
        },
        "datasheet": {
            "titles": ["Product Datasheet: TX-200 Sensor Module", "Technical Specification: Flow Controller FC-9", "Datasheet: Compact Power Supply PS-45"],
            "header": ["Revision 3 · Engineering release", "Document number DS-0412", "Preliminary specification"],
            "sentences": [
                "Operating voltage ranges from 3.0 to 5.5 volts.",
                "The module communicates via I2C and SPI interfaces.",
                "Typical power consumption is below twelve milliwatts.",
                "Operating temperature range is minus twenty to plus seventy degrees Celsius.",
                "The housing meets the IP54 protection standard.",
                "Calibration data is stored in on-board memory.",
                "Mounting holes are compatible with the previous product generation.",
                "Refer to the application note for wiring examples.",
                "Specifications are subject to change without notice.",
                "Ordering information is provided in the final section.",
            ],
        },
    },
    "de": {
        "paper": {
            "titles": [
                "Robuste Schätzung dünnbesetzter Signale unter adversarialem Rauschen",
                "Graphneuronale Netze zur Verkehrsprognose in mittelgroßen Städten",
                "Vergleich von Tokenisierern für ressourcenarme Sprachen",
                "Energieeffiziente Ablaufplanung für Edge-Inferenzcluster",
            ],
            "header": ["A. Lindqvist, M. Okafor, J. Brandt", "R. Moreau und T. Hayashi", "S. Patel, L. Kowalski"],
            "sentences": [
                "Wir untersuchen die Schätzung eines dünnbesetzten Vektors aus wenigen verrauschten Messungen.",
                "Unser Verfahren beruht auf konvexen Relaxierungen und liefert gute Rekonstruktionsgarantien.",
                "Experimente auf drei öffentlichen Datensätzen bestätigen die theoretischen Ergebnisse.",
                "Code und Vorverarbeitungsskripte werden zur Reproduzierbarkeit veröffentlicht.",
                "Frühere Arbeiten betrachten meist den rauschfreien Fall, der in der Praxis selten auftritt.",
                "Der vorgeschlagene Schätzer ist effizient und einfach zu implementieren.",
                "Wir diskutieren Grenzen des Ansatzes und skizzieren zukünftige Arbeiten.",
                "Alle Hyperparameter wurden auf einem separaten Validierungsdatensatz gewählt.",
                "Die Ergebnisse sind über fünf Zufallsinitialisierungen stabil.",
                "Abschnitt 2 fasst verwandte Arbeiten zusammen, Abschnitt 3 stellt das Modell vor.",
            ],
        },
        "cv": {
            "titles": ["Lebenslauf", "Bewerbungsprofil"],
            "header": ["Jana Ellerbrock · Datenanalystin", "Mehmet Aydın · Softwareentwickler", "Lena Hofmann · UX-Designerin"],
            "sentences": [
                "Fünf Jahre Erfahrung im Aufbau von Datenpipelines für Logistik- und Handelskunden.",
                "Leitung der Migration einer veralteten Reporting-Lösung in ein Cloud-Data-Warehouse.",
                "Kenntnisse: Python, SQL, Airflow, Docker, Kommunikation mit Fachabteilungen.",
                "Master of Science in Informatik mit Auszeichnung.",
                "Betreuung von drei Nachwuchskräften und Einführung von Code-Review-Richtlinien.",
                "Verkürzung der nächtlichen Batch-Laufzeit um vierzig Prozent.",
                "Sprachen: Deutsch (Muttersprache), Englisch (verhandlungssicher).",
                "Ehrenamtliche Tätigkeit als Kursleiterin für Programmiereinsteiger.",
                "Zertifizierung im agilen Projektmanagement.",
                "Referenzen auf Anfrage.",
            ],
        },
        "memo": {
            "titles": ["Interne Mitteilung: Quartalsstand", "Projektstand Lagerautomatisierung", "Protokoll: Lieferantenbewertung"],
            "header": ["An: Betriebsteam · Von: K. Brückner", "An: Lenkungskreis · Von: Projektbüro", "Verteiler: Finanzen, Einkauf"],
            "sentences": [
                "Die Einführung der neuen Scanner liegt im Zeitplan für das Quartalsende.",
                "Zwei Lieferanten haben vollständige Angebote eingereicht, der dritte bat um Verlängerung.",
                "Das Budget ist zu zweiundsechzig Prozent ausgeschöpft.",
                "Die Schulungen für die Nachtschicht finden nächste Woche statt.",
                "Bitte reichen Sie offene Rechnungen bis Monatsende ein.",
                "Das Sicherheitsaudit ergab keine kritischen Befunde.",
                "Bei Ersatzteilen rechnen wir mit Lieferverzögerungen von bis zu zwei Wochen.",
                "Die nächste Besprechung findet am ersten Montag des Monats statt.",
                "Die offenen Punkte stehen in der beigefügten Tabelle.",
                "Rückfragen bitte an das Projektbüro.",
            ],
        },
        "datasheet": {
            "titles": ["Datenblatt: Sensormodul TX-200", "Technische Spezifikation: Durchflussregler FC-9"],
            "header": ["Revision 3 · Freigabe Entwicklung", "Dokumentnummer DB-0412"],
            "sentences": [
                "Die Betriebsspannung liegt zwischen 3,0 und 5,5 Volt.",
                "Das Modul kommuniziert über I2C- und SPI-Schnittstellen.",
                "Die typische Leistungsaufnahme liegt unter zwölf Milliwatt.",
                "Der Betriebstemperaturbereich reicht von minus zwanzig bis plus siebzig Grad Celsius.",
                "Das Gehäuse erfüllt die Schutzart IP54.",
                "Kalibrierdaten werden im internen Speicher abgelegt.",
                "Die Befestigungsbohrungen sind mit der Vorgängergeneration kompatibel.",
                "Anschlussbeispiele finden sich im Applikationshinweis.",
                "Technische Änderungen vorbehalten.",
                "Bestellinformationen stehen im letzten Abschnitt.",
            ],
        },
    },
}


def compose(rng: random.Random, lang: str, genre: str) -> dict:
    bank = TEXT[lang][genre]
    sents = list(bank["sentences"])
    rng.shuffle(sents)
    n1, n2 = rng.randint(3, 4), rng.randint(3, 4)
    return {
        "title": rng.choice(bank["titles"]),
        "header": rng.choice(bank["header"]),
        "paragraphs": [" ".join(sents[:n1]), " ".join(sents[n1:n1 + n2])],
    }
