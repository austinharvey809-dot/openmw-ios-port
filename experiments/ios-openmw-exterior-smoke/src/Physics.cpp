#include "Physics.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace G3 {
Physics::Physics(){
    broadphase.getOverlappingPairCache()->setInternalGhostPairCallback(&pairs);
    ghost.setCollisionShape(&capsule);ghost.setCollisionFlags(btCollisionObject::CF_CHARACTER_OBJECT);
    world.addCollisionObject(&ghost,btBroadphaseProxy::CharacterFilter,btBroadphaseProxy::StaticFilter);
    world.addAction(&character);character.setGravity(btVector3(0,0,-627.2));
    character.setMaxSlope(49*3.14159265358979323846/180);character.setFallSpeed(1000);
}
Physics::~Physics(){
    world.removeAction(&character);world.removeCollisionObject(&ghost);
    for(auto& object:objects)world.removeCollisionObject(object.get());
    broadphase.getOverlappingPairCache()->setInternalGhostPairCallback(nullptr);
}
void Physics::add(std::shared_ptr<const Resource::BulletShape> source,const osg::Matrix& matrix){
    // Upstream PhysicsSystem maps NC/NCC meshes to visual/camera-only groups.
    // This capsule is an actor; it must not collide with either group.
    if(!source||!source->mCollisionShape||source->mVisualCollisionType!=Resource::VisualCollisionType::None){++collisionless;return;}
    auto shape=Resource::makeInstance(source);
    osg::Vec3d p,scale;osg::Quat q,orientation;matrix.decompose(p,q,scale,orientation);
    if(!std::isfinite(scale.x())||scale.x()<=0||std::abs(scale.x()-scale.y())>1e-3||std::abs(scale.x()-scale.z())>1e-3)
        throw std::runtime_error("G3 collision requires uniform positive reference scale");
    shape->setLocalScaling(btVector3(scale.x(),scale.y(),scale.z()));
    auto object=std::make_unique<btCollisionObject>();object->setCollisionShape(shape->mCollisionShape.get());
    object->setWorldTransform(btTransform(btQuaternion(q.x(),q.y(),q.z(),q.w()),btVector3(p.x(),p.y(),p.z())));
    object->setCollisionFlags(btCollisionObject::CF_STATIC_OBJECT);
    world.addCollisionObject(object.get(),btBroadphaseProxy::StaticFilter,btBroadphaseProxy::CharacterFilter);
    templates.push_back(std::move(source));shapes.push_back(std::move(shape));objects.push_back(std::move(object));
}
void Physics::addTerrain(Resource::CollisionShapePtr shape){
    if(!shape)throw std::runtime_error("Missing terrain collision");
    auto object=std::make_unique<btCollisionObject>();object->setCollisionShape(shape.get());
    object->setWorldTransform(btTransform::getIdentity());object->setCollisionFlags(btCollisionObject::CF_STATIC_OBJECT);
    world.addCollisionObject(object.get(),btBroadphaseProxy::StaticFilter,btBroadphaseProxy::CharacterFilter);
    terrain.push_back(std::move(shape));objects.push_back(std::move(object));
}
void Physics::start(const osg::Vec3d& feet){
    for(unsigned i=0;i<3;++i)if(!std::isfinite(feet[i]))throw std::runtime_error("Nonfinite physics spawn");
    character.reset(&world);character.warp(btVector3(feet.x(),feet.y(),feet.z()+48));accumulator=0;
}
osg::Vec3d Physics::move(const osg::Vec3d& velocity,double dt){
    for(unsigned i=0;i<3;++i)if(!std::isfinite(velocity[i]))throw std::runtime_error("Nonfinite walking velocity");
    if(!std::isfinite(dt)||dt<0)throw std::runtime_error("Invalid physics time");
    const double elapsed=std::min(dt,MaxFrameDelta);droppedSeconds+=dt-elapsed;accumulator+=elapsed;
    constexpr double step=FixedStep;
    unsigned frameSteps=0;
    while(accumulator>=step&&frameSteps<MaxFrameSteps){
        character.setWalkDirection(btVector3(velocity.x()*step,velocity.y()*step,0));
        world.stepSimulation(step,0);accumulator-=step;++steps;++frameSteps;
    }
    if(accumulator>=step){droppedSeconds+=accumulator;accumulator=0;}
    const auto p=ghost.getWorldTransform().getOrigin();return {p.x(),p.y(),p.z()+40};
}
}
