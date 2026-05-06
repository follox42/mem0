# OpenMemory Taxonomy — Nolann Stack

> Reference doc qui explique le modele 5-niveaux d'organisation de la memoire dans cette installation. Lue par les agents IA, par toi (Nolann), et par tout dev qui contribue.

**Repo :** [follox42/mem0](https://github.com/follox42/mem0)
**Branch live :** `main` (deploye sur Coolify, FQDN `mcp-memory.nocode18.com`)
**Plane project :** `MEM` (OpenMemory Stack)
**KB Obsidian :** `projects/openmemory-stack/_SYSTEM.md`

---

## TLDR

La memoire d'un agent ne doit PAS etre organisee a un seul niveau. mem0 expose 5 dimensions natives qu'on combine :

| # | Niveau | Role | Modifiable | Exemples |
|---|---|---|---|---|
| 1 | `user_id` | Personne (HARD isolation) | non | nolann, jess, yoann, matt, djamila |
| 2 | `app_id` | Espace macro (ACL) | rare | perso, business, tools, learn, shared, inbox |
| 3 | `categories` | Taxonomie semantique (auto-classifiee LLM) | oui (reclassifiable) | sante, nocode18, openfang, trading-quant, ... |
| 4 | `metadata.tags` | Tags libres transverses | libre a la volee | client-laura, urgent, Q2-2026, public, ... |
| 5 | graph (Neo4j) | Entites + relations | auto-extract | (Person)-[FOUNDED]->(Company) |

---

## Niveau 1 — `user_id` (5 personnes)

Isolation **HARD** : aucune fuite entre users. Forced par filtre Postgres FK + Qdrant payload.

| user_id | qui | apps |
|---|---|---|
| `nolann` | toi (owner) | perso, business, tools, learn, shared, inbox |
| `jess` | famille | personal |
| `yoann` | famille | personal |
| `matt` | famille | personal |
| `djamila` | famille | personal |

---

## Niveau 2 — `app_id` (6 macro-espaces pour Nolann)

Frontiere structurelle avec **ACL configurable**. Une memory appartient a UNE app a la fois (FK Postgres). Pour decider de l'app : prefixe `[app]` dans `add_memories(text)` ou app par defaut de l'agent.

| App | Description | shared_default |
|---|---|---|
| `perso` | Vie privee (sante, famille, finances perso, journal) | non |
| `business` | Toutes entreprises + sales transverse (NoCode18, Zephly, Freelance, Upwork) | non |
| `tools` | Infra technique que je construis/opere (OpenFang, MCPs, trading bot, infra) | non |
| `learn` | Connaissances acquises (transverse par nature) | **oui** |
| `shared` | Identite, profils sociaux, prefs globales (lue par tous mes agents) | **oui** |
| `inbox` | Capture brute pas-encore-classifiee | non |

### Pourquoi 6 et pas plus ?

La V1 etait `priv-perso`, `priv-finance`, `pro-nocode18`, `pro-zephly`, `tools-trading`, `tools-infra`, `learn-tech`, `learn-business`, etc. -> 14 apps prefixees.

Probleme : les prefixes (`priv-`, `pro-`, `tools-`) **simulent** une hierarchie qui devrait vivre au niveau **categories** (niveau 3, dynamique et reclassifiable), pas au niveau **apps** (niveau 2, structurel et stable).

Resolu en V2 : 6 apps macro stables + 31 categories fines reclassifiables.

### Quand creer une nouvelle app ?

Rare. Critere : tu as besoin d'une **frontiere ACL distincte**, pas d'une simple categorisation. Exemples valides :
- Tu lances une 6eme entreprise totalement separee -> nouvelle app si vraiment isolee, sinon `business` + nouvelle category
- Tu veux un espace que JAMAIS aucun agent autre que toi ne lise -> oui (mais utilise plutot un user_id distinct)

Quand creer une **category** plutot : 95% des cas. Voir niveau 3.

---

## Niveau 3 — `categories` (31 custom categories)

C'est ici que vit la **granularite metier**. Chaque memory est auto-classifiee par mem0 (LLM gpt-4o-mini) dans 1 a 5 categories. Stockee dans la table Postgres `categories` + duppliquee dans `metadata.categories` pour filtrage rapide.

La liste complete vit dans [`config/categories.yaml`](config/categories.yaml). 31 categories regroupees en 8 axes :

### Vie perso (5)
`sante` | `famille` | `finance-perso` | `journal` | `entertainment`

### Business / entreprises (5)
`nocode18` | `zephly` | `freelance` | `upwork` | `poker-stake`

### Sales / Growth / Marketing (5)
`prospection` | `copywriting` | `marketing` | `content` | `seo-aeo`

### Outils techniques (7)
`openfang` | `openclaw` | `openmemory` | `social-os` | `mcps` | `web-stealth` | `infra-devops`

### Trading (2)
`trading-quant` | `trading-knowledge`

### Apprentissage (4)
`learn-tech` | `learn-systems` | `learn-security` | `bts-ciel`

### Meta / system (3)
`kb-system` | `legal-fr` | `decision-retro`

### Justification de la liste

Synthese de 4 sources (sub-agents Plane + KB Obsidian + filesystem + memory files) :

| Source | Volume | Categories suggerees |
|---|---|---|
| Plane | 23 projets actifs, 5 initiatives Q2 2026 | 22 (synthese par sub-agent) |
| KB Obsidian | 36 sous-dossiers `projects/`, 17 `knowledge/`, 5 `areas/` | 22 (synthese par sub-agent) |
| Filesystem | 50+ repos, 6 services Docker | confirme cluster Agent OS + MCPs |
| Memory files | 2 entries (web-stealth + Plane mgmt) | confirme priorites recentes |

31 categories = compromis entre granularite (Plane = 22-23 domaines distincts) et evitement de l'inflation (au-dela de 40, le LLM hesite et la classification se degrade).

### Quand ajouter une nouvelle category ?

Criteres :
1. **Volume** : tu as deja >= 10 memories qui parlent de ce sujet et qu'aucune category existante ne capture
2. **Distinction semantique** : ce n'est ni un sous-cas d'une autre category, ni un tag transverse
3. **Stabilite** : ce sujet va exister dans 6 mois (sinon, c'est un tag)

**Comment ajouter** :
1. Editer `config/categories.yaml`
2. Restart le container API (le cache se reset)
3. Le LLM utilisera la nouvelle taxonomie pour les futures memories

### Quand reclassifier l'historique ?

Si tu fusionnes/splittes des categories, lancer une re-categorization batch sur les memories existantes (endpoint a implementer en MEM-7 si besoin). Sinon les anciennes memories conservent leurs anciennes labels (acceptable).

---

## Niveau 4 — `metadata.tags` (libres, transverses)

Les tags sont LIBRES (pas de YAML config) et **transverses** : ils traversent les apps et categories. Ajoutes via l'outil MCP `tag_memory(memory_id, tags=[...])`.

### Bons usages

| Type de tag | Exemples |
|---|---|
| Client / contact specifique | `client-laura`, `lead-jean-dupont` |
| Periode | `Q2-2026`, `mai-2026`, `S20` |
| Visibilite | `public`, `confidentiel`, `nda` |
| Etat / urgence | `urgent`, `archived`, `wip` |
| Provenance | `from-twitter`, `from-podcast`, `meeting-call` |
| Theme transverse | `viralite`, `dette-tech`, `lecon-sales` |

### Mauvais usages (faire en categories ou apps a la place)

- ❌ `pro-nocode18` -> `nocode18` est une category
- ❌ `priv-` ou `tools-` -> les apps font deja ca
- ❌ Tags trop specifiques jamais reutilises (`bug-auth-2026-mars`)

---

## Niveau 5 — graph memory (Neo4j, auto)

mem0 extrait automatiquement les **entites** (Person, Company, Concept, Tool) et leurs **relations** (FOUNDED, USES, PREFERS) a chaque `add_memories`. Stockees dans Neo4j (graph_store auto-active si `NEO4J_URL` set).

### Cas d'usage

- *"Donne-moi tout ce qui touche a Laura"* -> requete Cypher multi-hop
- *"Quels concepts sont lies a Zephly ?"* -> traverse les `WORKS_ON`, `BUILT_WITH`, etc.
- *"Qui a fonde quoi ?"* -> `MATCH (p:Person)-[:FOUNDED]->(c:Company)`

Inspectable via Neo4j Browser sur `:7474` (creds dans Vaultwarden, secret `openmemory-neo4j`).

### Quand utiliser le graph vs vector ?

| Question | Outil |
|---|---|
| "Qu'est-ce qui RESSEMBLE a X ?" (semantique) | Qdrant (vector) |
| "Qu'est-ce qui est CONNECTE a X ?" (relationnel) | Neo4j (graph) |
| "Qu'est-ce qui touche au business ET parle de Laura ?" | combine app/categories filter (Postgres) + graph traversal |

---

## Decisions de design

### Pourquoi pas plus de niveaux ?

5 c'est deja beaucoup. Aller au-dela (sub-categories hierarchiques, namespaces, etc.) explose la complexite mentale et de classification LLM. La regle : **si une dimension peut etre exprimee comme un tag, ne la promouvoir au niveau category/app que si elle a un usage structurel justifie**.

### Pourquoi pas moins ?

Moins de niveaux = perte d'expressivite. Sans `categories`, on tomberait dans le piege du V1 (preposer sur app). Sans `tags`, on saturerait categories avec des notions transverses (`urgent`, `client-X`).

### Pourquoi `learn` est `shared_default: true` mais pas `business` ?

- `learn` = connaissance reutilisable across all contexts (un concept de design pattern profite a `dev-zephly` ET `ops-nocode18`)
- `business` = info specifique a une entreprise (un client de NoCode18 n'interesse pas Zephly)

Les apps `shared_default: true` sont lues PAR DEFAUT par tous les agents Nolann -> il faut limiter ca au strict transverse, sinon on annule l'isolation.

### Pourquoi 31 categories et pas 50 ?

Les papers mem0 et la doc officielle convergent : **20-40 categories** est le sweet spot pour gpt-4o-mini. Au-dela, le modele hesite et la classification rate. En-dessous, on perd de la finesse.

31 = tient sur un seul prompt, donne un signal de classification fiable, couvre tous les domaines actifs.

### Pourquoi `inbox` comme app ET fallback de categorie ?

- App `inbox` = tu y stockes EXPLICITEMENT (ex: `[inbox] truc a trier plus tard`)
- Category `inbox` (fallback) = le LLM y route quand AUCUNE des 31 categories ne fit clairement

Les deux jouent le meme role (capture + tri ulterieur), mais a deux niveaux differents. Tri periodique : procedure `proc-tri-inbox` a ecrire dans la KB.

---

## Routing pratique — comment ecrire une memory

### Cas 1 — agent ecrit dans son app par defaut

```
add_memories("j'ai discute avec Laura sur le projet refonte")
```
Si l'agent est `ops-nocode18`, ecrit dans app `business`, le LLM categorise probablement `nocode18` + `client-laura` (tag).

### Cas 2 — explicit via prefixe `[app]`

```
add_memories("[shared] mon Twitter c'est @follox42, principal canal de visibilite")
```
Force l'app `shared`. Le LLM categorise probablement `content` + `marketing`.

### Cas 3 — promotion post-hoc

```
promote_memory(memory_id)
```
Deplace de l'app courante vers `shared`. Utile quand tu realises qu'une info perso est en fait transverse.

### Cas 4 — re-categorization

```
move_memory(memory_id, target_app="learn")
tag_memory(memory_id, tags=["oauth", "deep-dive"])
```

---

## FAQ

### Q: Une memory peut avoir plusieurs categories ?
**Oui.** Le LLM en attribue 1 a 5. Stockees dans `metadata.categories` (array) + table `memory_categories` (m2m).

### Q: Qu'est-ce qui est unique pour une memory ?
App_id (FK strict) ET user_id (FK strict). Categories et tags peuvent etre N.

### Q: Comment chercher dans une categorie precise ?
```python
m.search("oauth", user_id="nolann", filters={"metadata.categories": {"$in": ["learn-security"]}})
```
Filtres v2 mem0 : `$in`, `$and`, `$or`, `$eq`, `$gt`, etc.

### Q: Comment voir tous les `client-laura` ?
```python
m.search("", user_id="nolann", filters={"metadata.tags": {"$in": ["client-laura"]}})
```

### Q: Que se passe-t-il si je modifie `categories.yaml` ?
- Restart container = nouveau prompt LLM = futures memories utilisent la nouvelle taxonomie
- Memories existantes conservent leurs anciennes categories tant qu'on ne lance pas la re-categorization batch

### Q: Comment ajouter un user a la famille ?
Editer `config/users.yaml` + `config/apps.yaml` (ajouter `<user>: [{name: personal}]`). Restart. Idempotent.

### Q: Pourquoi pas une UI pour gerer la taxonomie ?
A voir en MEM-8. Pour l'instant le YAML est plus rapide (et trackable via git).

---

## Evolution future

Work items prevus dans Plane projet `MEM` :
- **MEM-7** : endpoint REST `POST /api/v1/memories/recategorize` pour re-classifier l'historique apres modif YAML
- **MEM-8** : UI categories management (CRUD via dashboard)
- **MEM-9** : suggested-tags via LLM (proposer 3-5 tags pertinents au moment de l'ecriture)
- **MEM-10** : analytics dashboard (top 10 categories, gaps, evolution dans le temps)

---

## Lecture liee (KB Obsidian)

- `projects/openmemory-stack/_INDEX.md` — etat courant
- `projects/openmemory-stack/_SYSTEM.md` — reference systeme
- `procedures/system/proc-spawn-agent.md` — spawn d'un agent
- `procedures/system/proc-create-memory-zone.md` — creer une app
- `procedures/system/proc-tri-inbox.md` (a ecrire) — tri periodique de l'inbox
- `system/06-agents/agent-registry.md` — catalogue des agents actifs
- `knowledge/ai/openmemory.md` — cours OpenMemory
- `knowledge/ai/mem0.md` — cours mem0
