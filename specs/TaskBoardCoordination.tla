---- MODULE TaskBoardCoordination ----
(*
Formal specification of dharma_swarm task board coordination.

Models the distributed task claiming, execution, and completion protocol
to verify safety and liveness properties.

Based on AWS TLA+ patterns for distributed systems.
*)

EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANTS
    Agents,         \* Set of agent IDs
    Tasks,          \* Set of task IDs
    MaxConcurrent   \* Maximum concurrent tasks per agent

VARIABLES
    task_status,    \* Tasks -> {"pending", "claimed", "running", "completed", "failed"}
    task_owner,     \* Tasks -> Agent ∪ {NULL}
    task_result,    \* Tasks -> Result ∪ {NULL}
    agent_state,    \* Agents -> {"idle", "working", "failed"}
    agent_tasks,    \* Agents -> Sequence of task IDs (active tasks)
    message_queue   \* Sequence of messages between agents

----

(*
Type invariant - ensures all variables stay in valid states.
*)
TypeOK ==
    /\ task_status ∈ [Tasks -> {"pending", "claimed", "running", "completed", "failed"}]
    /\ task_owner ∈ [Tasks -> Agents ∪ {NULL}]
    /\ task_result ∈ [Tasks -> STRING ∪ {NULL}]
    /\ agent_state ∈ [Agents -> {"idle", "working", "failed"}]
    /\ agent_tasks ∈ [Agents -> Seq(Tasks)]
    /\ message_queue ∈ Seq([type: STRING, from: Agents, to: Agents, task: Tasks])

(*
Initial state - all tasks pending, all agents idle.
*)
Init ==
    /\ task_status = [t ∈ Tasks |-> "pending"]
    /\ task_owner = [t ∈ Tasks |-> NULL]
    /\ task_result = [t ∈ Tasks |-> NULL]
    /\ agent_state = [a ∈ Agents |-> "idle"]
    /\ agent_tasks = [a ∈ Agents |-> << >>]
    /\ message_queue = << >>

----

(*
Agent claims a pending task.

Preconditions:
- Task must be pending
- Agent must have capacity (< MaxConcurrent tasks)
- Agent must not have failed

Postconditions:
- Task status becomes "claimed"
- Task is owned by the agent
- Agent's task list includes the task
*)
ClaimTask(agent, task) ==
    /\ task_status[task] = "pending"
    /\ Len(agent_tasks[agent]) < MaxConcurrent
    /\ agent_state[agent] # "failed"
    /\ task_status' = [task_status EXCEPT ![task] = "claimed"]
    /\ task_owner' = [task_owner EXCEPT ![task] = agent]
    /\ agent_tasks' = [agent_tasks EXCEPT ![agent] = Append(@, task)]
    /\ UNCHANGED <<task_result, agent_state, message_queue>>

(*
Agent starts executing a claimed task.
*)
StartTask(agent, task) ==
    /\ task_status[task] = "claimed"
    /\ task_owner[task] = agent
    /\ task_status' = [task_status EXCEPT ![task] = "running"]
    /\ agent_state' = [agent_state EXCEPT ![agent] = "working"]
    /\ UNCHANGED <<task_owner, task_result, agent_tasks, message_queue>>

(*
Agent completes a task successfully.

Postconditions:
- Task status becomes "completed"
- Task has a result
- Task is removed from agent's active list
- Agent becomes idle if no other tasks
*)
CompleteTask(agent, task, result) ==
    /\ task_status[task] = "running"
    /\ task_owner[task] = agent
    /\ task_status' = [task_status EXCEPT ![task] = "completed"]
    /\ task_result' = [task_result EXCEPT ![task] = result]
    /\ LET remaining_tasks == SelectSeq(agent_tasks[agent], LAMBDA t: t # task)
       IN /\ agent_tasks' = [agent_tasks EXCEPT ![agent] = remaining_tasks]
          /\ agent_state' = [agent_state EXCEPT ![agent] =
                IF Len(remaining_tasks) = 0 THEN "idle" ELSE "working"]
    /\ UNCHANGED <<task_owner, message_queue>>

(*
Task fails during execution.

Postconditions:
- Task status becomes "failed"
- Task is removed from agent's list
- Agent continues (doesn't fail unless all tasks fail)
*)
FailTask(agent, task, reason) ==
    /\ task_status[task] ∈ {"claimed", "running"}
    /\ task_owner[task] = agent
    /\ task_status' = [task_status EXCEPT ![task] = "failed"]
    /\ task_result' = [task_result EXCEPT ![task] = reason]
    /\ LET remaining_tasks == SelectSeq(agent_tasks[agent], LAMBDA t: t # task)
       IN /\ agent_tasks' = [agent_tasks EXCEPT ![agent] = remaining_tasks]
          /\ agent_state' = [agent_state EXCEPT ![agent] =
                IF Len(remaining_tasks) = 0 THEN "idle" ELSE "working"]
    /\ UNCHANGED <<task_owner, message_queue>>

(*
Agent fails completely (loses all claimed tasks).
*)
AgentFail(agent) ==
    /\ agent_state[agent] # "failed"
    /\ agent_state' = [agent_state EXCEPT ![agent] = "failed"]
    /\ LET agent_claimed_tasks == {t ∈ Tasks : task_owner[t] = agent}
       IN /\ task_status' = [t ∈ Tasks |->
                IF t ∈ agent_claimed_tasks ∧ task_status[t] # "completed"
                THEN "pending"  \* Release back to pending
                ELSE task_status[t]]
          /\ task_owner' = [t ∈ Tasks |->
                IF t ∈ agent_claimed_tasks ∧ task_status[t] # "completed"
                THEN NULL
                ELSE task_owner[t]]
    /\ agent_tasks' = [agent_tasks EXCEPT ![agent] = << >>]
    /\ UNCHANGED <<task_result, message_queue>>

----

(*
All possible next states.
*)
Next ==
    \/ ∃ a ∈ Agents, t ∈ Tasks : ClaimTask(a, t)
    \/ ∃ a ∈ Agents, t ∈ Tasks : StartTask(a, t)
    \/ ∃ a ∈ Agents, t ∈ Tasks, r ∈ STRING : CompleteTask(a, t, r)
    \/ ∃ a ∈ Agents, t ∈ Tasks, r ∈ STRING : FailTask(a, t, r)
    \/ ∃ a ∈ Agents : AgentFail(a)

----
(*
=============================================================================
SAFETY PROPERTIES (Invariants that must always hold)
=============================================================================
*)

(*
CRITICAL: No task can have multiple owners.

This prevents duplicate work and ensures task isolation.
*)
NoTaskDuplication ==
    ∀ t1, t2 ∈ Tasks :
        (task_owner[t1] # NULL ∧ task_owner[t2] # NULL ∧ task_owner[t1] = task_owner[t2] ∧ t1 # t2)
        => (task_status[t1] ∈ {"completed", "failed"} ∨ task_status[t2] ∈ {"completed", "failed"})

(*
Every claimed/running task has an owner.
*)
ClaimedTasksHaveOwner ==
    ∀ t ∈ Tasks :
        task_status[t] ∈ {"claimed", "running"}
        => task_owner[t] # NULL

(*
Completed tasks have results.
*)
CompletedTasksHaveResults ==
    ∀ t ∈ Tasks :
        task_status[t] = "completed"
        => task_result[t] # NULL

(*
Agent capacity is never exceeded.
*)
AgentCapacityRespected ==
    ∀ a ∈ Agents :
        Len(agent_tasks[a]) ≤ MaxConcurrent

(*
Failed agents own no tasks.
*)
FailedAgentsHaveNoTasks ==
    ∀ a ∈ Agents :
        agent_state[a] = "failed"
        => Len(agent_tasks[a]) = 0

(*
Task ownership consistency: If agent owns task, task is in agent's list.
*)
OwnershipConsistency ==
    ∀ a ∈ Agents, t ∈ Tasks :
        (task_owner[t] = a ∧ task_status[t] ∈ {"claimed", "running"})
        => ∃ i ∈ 1..Len(agent_tasks[a]) : agent_tasks[a][i] = t

----
(*
=============================================================================
LIVENESS PROPERTIES (Progress guarantees)
=============================================================================
*)

(*
Eventually, all pending tasks are either completed or failed
(assuming at least one non-failed agent exists).
*)
EventualCompletion ==
    (∃ a ∈ Agents : agent_state[a] # "failed")
    =>
    ∀ t ∈ Tasks :
        task_status[t] = "pending"
        ~> task_status[t] ∈ {"completed", "failed"}

(*
If a task is claimed, it eventually reaches a terminal state.
*)
ClaimedTasksEventuallyComplete ==
    ∀ t ∈ Tasks :
        task_status[t] = "claimed"
        ~> task_status[t] ∈ {"completed", "failed"}

(*
If all agents fail, no task remains claimed.
*)
NoStuckTasks ==
    (∀ a ∈ Agents : agent_state[a] = "failed")
    =>
    (∀ t ∈ Tasks : task_status[t] ∈ {"pending", "completed", "failed"})

----
(*
=============================================================================
SPECIFICATION
=============================================================================
*)

(*
System specification with fairness constraints.

Weak fairness: If an action is continuously enabled, it will eventually happen.
Strong fairness: If an action is infinitely often enabled, it will eventually happen.
*)
Spec == Init ∧ □[Next]_<<task_status, task_owner, task_result, agent_state, agent_tasks, message_queue>>
            ∧ WF_<<task_status, task_owner, task_result, agent_state, agent_tasks, message_queue>>(Next)

====
