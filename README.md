# DO NOT USE THIS
# DO NOT USE THIS
# DO NOT USE THIS
# DO NOT USE THIS
# DO NOT USE THIS
# DO NOT USE THIS
# DO NOT USE THIS
# DO NOT USE THIS
# DO NOT USE THIS

# WORK IN PROGRESS (that will probably never be finished)

It is not usable at the moment because anonimatron 1.9.4-SNAPSHOT or 1.9.3 will not anonymise these

* notification_blueprints
  * `ERROR: syntax error at or near "group"`
* settings
  * `PSQLException: ERROR: syntax error at or near "default"`
* subnets
  * `PSQLException: ERROR: syntax error at or near "from"`
* nics
  * `Can not generate a random hex string with length 15. Generated String size is 16 characters.`
* dynflow_delayed_plans
  * no primary key (it has a fkey constraint against dynflow_execution_plans)  
* operating_systems
  * key too long  

I started doing this so I could anonymise a foreman database - but
in the end the devs found the bug without the database so I stopped 
working on it.

So it's likely nothing in here will work (although I have run the DomainAnonymizer
across some of the database tables)


# From here down is the WIP - 

# Anonymizers for anonimatron

These are anonymisers written to anonymise a [foreman](http://www.theforeman.org) database 
using [anonimatron](https://realrolfje.github.io/anonimatron/).

The purpose is so a database can be provided to the foreman developers
to help them reproduce a problem.

At the moment there is only one anonymizer - DOMAIN which will
replace a domain name with a faked one.

**THERE IS NO GUARANTEE SOME SENSITIVE INFORMATION WILL NOT LEAK!!**

You **MUST** check the resulting database to make sure nothing sensitive 
is in there.

**WARNING** anonimatron anonymises the database **IN PLACE**. 

In other words - do not connect to your live foreman database!

## Installation

Get and install the latest binary release of anonimatron from [here](https://realrolfje.github.io/anonimatron/).
 
Copy the [library jar file](libraries/anonymizers-1.0-SNAPSHOT.jar) into the 
libraries subdirectory of your unpack of the release zip file.

Copy [foreman.xml](resources/configs/foreman.xml) and set your 
database password on the password attribute of the configuration element.

## Anonymising your database.

1. Dump your live foreman database with pg_dumpall
1. Setup a local postgres database server 
1. Load the dumped database into your local empty server.
1. Change the password of the foreman database user so you can give it to the devs.
1. Empty out some big tables that should not be needed by the devs.
1. Run anonimatron on your local database server.
1. Dump the resulting database

## Big tables to remove or at least shrink

```postgresql
delete from audits;
delete from reports;
```

The fact tables can get enormous too - we have 167,000 fact_names and about 
2 million fact_values.

### fact_names and fact_values

Have to remove the key constraints before deleting fact_names records.

Find the key constraints on the table which depends on fact_names:

```postgresql

\d fact_values
                                      Table "public.fact_values"
    Column    |            Type             |                        Modifiers                         
--------------+-----------------------------+----------------------------------------------------------
 id           | bigint                      | not null default nextval('fact_values_id_seq'::regclass)
 value        | text                        | 
 fact_name_id | integer                     | not null
 host_id      | integer                     | not null
 updated_at   | timestamp without time zone | 
 created_at   | timestamp without time zone | 
Indexes:
    "fact_values_pkey" PRIMARY KEY, btree (id)
    "index_fact_values_on_fact_name_id_and_host_id" UNIQUE, btree (fact_name_id, host_id)
    "index_fact_values_on_fact_name_id" btree (fact_name_id)
    "index_fact_values_on_host_id" btree (host_id)
Foreign-key constraints:
    "fact_values_fact_name_id_fk" FOREIGN KEY (fact_name_id) REFERENCES fact_names(id)
    "fact_values_host_id_fk" FOREIGN KEY (host_id) REFERENCES hosts(id)

```

Remove the constraints

```postgresql
alter table fact_values
drop constraint fact_values_fact_name_id_fk,
add constraint 
  fact_values_fact_name_id_fk  FOREIGN KEY (fact_name_id) REFERENCES fact_names(id)
  on delete cascade ;
  
alter table fact_values
drop constraint fact_values_host_id_fk,
add constraint 
  fact_values_host_id_fk  FOREIGN KEY (host_id) REFERENCES hosts(id)
  on delete cascade ;
```

Delete all but 20 fact_names

```postgresql
  
  select count(*) from fact_names;
/*  
 count  
--------
 167666
(1 row)
*/

-- at most 20 will be deleted
delete from fact_names 
where ctid in 
   (
     select ctid 
     from fact_names 
     limit (-1 * (20 - (select count(*) from fact_names))));
```

### hosts

Remove the foreign key constraints

```postgresql
alter table host_status
drop constraint host_status_hosts_host_id_fk,
add constraint 
  host_status_hosts_host_id_fk  FOREIGN KEY (host_id) REFERENCES hosts(id) on delete cascade ;

alter table nics
drop constraint nics_host_id_fk,
add constraint 
  nics_host_id_fk FOREIGN KEY (host_id) REFERENCES hosts(id) on delete cascade ;

alter table host_classes
drop constraint host_classes_host_id_fk,
add constraint 
  host_classes_host_id_fk FOREIGN KEY (host_id) REFERENCES hosts(id) on delete cascade ;
```

Delete all but 20 of them

```postgresql
  
-- leave only 20 hosts behind
  
delete from hosts 
where ctid in (select ctid from hosts limit (-1 * (20 - (select count(*) from hosts)))) ;
```
